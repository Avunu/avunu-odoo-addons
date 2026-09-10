# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from odoo.tests.common import tagged
from odoo.tools import mute_logger

from odoo.addons.mail_gateway.tests.common import MailGatewayTestCase

CONTROLLER_LOGGER = "odoo.addons.mail_gateway_twilio.controllers.gateway"
MODEL_LOGGER = "odoo.addons.mail_gateway_twilio.models.mail_gateway_twilio"


@tagged("-at_install", "post_install")
class TestMailGatewayTwilio(MailGatewayTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.webhook = "twilio_hook"
        cls.gateway = cls.env["mail.gateway"].create(
            {
                "name": "Twilio",
                "gateway_type": "twilio",
                "token": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # Account SID
                "webhook_secret": "auth-token",  # Auth Token
                "twilio_from_number": "+15550000000",
                "webhook_key": cls.webhook,
                "member_ids": [(4, cls.env.user.id)],
            }
        )
        # Skip the network round-trip of set_webhook(); mark it integrated.
        cls.gateway.integrated_webhook_state = "integrated"
        cls.customer_number = "+34699999999"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _webhook_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return "{}/gateway/twilio/{}/update".format(base.rstrip("/"), self.webhook)

    def _signature(self, params):
        data = self._webhook_url() + "".join(
            f"{key}{value}" for key, value in sorted(params.items())
        )
        return base64.b64encode(
            hmac.new(
                self.gateway.webhook_secret.encode(), data.encode(), hashlib.sha1
            ).digest()
        ).decode()

    def _post(self, params, signature=True):
        headers = {}
        if signature is True:
            headers["X-Twilio-Signature"] = self._signature(params)
        elif signature:  # explicit (wrong) value
            headers["X-Twilio-Signature"] = signature
        return self.url_open(
            f"/gateway/twilio/{self.webhook}/update", data=params, headers=headers
        )

    def _inbound(self, body="Hello shop", number=None, extra=None):
        params = {
            "MessageSid": "SMinbound1",
            "From": number or self.customer_number,
            "To": "+15550000000",
            "Body": body,
            "NumMedia": "0",
            "SmsStatus": "received",
        }
        if extra:
            params.update(extra)
        return params

    def _channel(self):
        return self.env["discuss.channel"].search(
            [("gateway_id", "=", self.gateway.id)]
        )

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------
    def test_receive_message_guest(self):
        self._post(self._inbound())
        channel = self._channel()
        self.assertTrue(channel)
        self.assertEqual(channel.gateway_channel_token, self.customer_number)
        message = channel.message_ids
        self.assertTrue(message)
        self.assertIn("Hello shop", message.body)
        # Unknown sender -> guest author (no partner)
        self.assertFalse(message.author_id)

    def test_receive_message_partner(self):
        partner = self.env["res.partner"].create(
            {"name": "DEMO", "mobile": self.customer_number}
        )
        self._post(self._inbound())
        message = self._channel().message_ids
        self.assertEqual(message.author_id, partner)
        # A partner<->gateway link is created for future routing.
        self.assertTrue(
            self.env["res.partner.gateway.channel"].search(
                [
                    ("gateway_id", "=", self.gateway.id),
                    ("gateway_token", "=", self.customer_number),
                    ("partner_id", "=", partner.id),
                ]
            )
        )

    def test_receive_mms(self):
        media = MagicMock()
        media.content = b"binary_data"
        media.raise_for_status.return_value = None
        with patch("requests.get", return_value=media):
            self._post(
                self._inbound(
                    body="Look",
                    extra={
                        "NumMedia": "1",
                        "MediaUrl0": "https://media.twilio.com/abc",
                        "MediaContentType0": "image/png",
                    },
                )
            )
        message = self._channel().message_ids
        self.assertTrue(message.attachment_ids)
        self.assertEqual(message.attachment_ids.mimetype, "image/png")

    def test_receive_mms_audio_is_voice(self):
        media = MagicMock()
        media.content = b"binary_data"
        media.raise_for_status.return_value = None
        with patch("requests.get", return_value=media):
            self._post(
                self._inbound(
                    body="",
                    extra={
                        "NumMedia": "1",
                        "MediaUrl0": "https://media.twilio.com/abc",
                        "MediaContentType0": "audio/ogg",
                    },
                )
            )
        message = self._channel().message_ids
        self.assertTrue(message.attachment_ids.voice_ids)

    @mute_logger(CONTROLLER_LOGGER)
    def test_receive_no_signature_rejected(self):
        self._post(self._inbound(), signature=False)
        self.assertFalse(self._channel())

    @mute_logger(CONTROLLER_LOGGER)
    def test_receive_wrong_signature_rejected(self):
        self._post(self._inbound(), signature="deadbeef")
        self.assertFalse(self._channel())

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------
    def _send_via_composer(self, gateway=None, mock=None):
        gateway = gateway or self.gateway
        partner = self.env["res.partner"].create(
            {"name": "Client", "mobile": self.customer_number}
        )
        composer = self.env["twilio.composer"].create(
            {
                "res_model": partner._name,
                "res_id": partner.id,
                "number_field_name": "mobile",
                "gateway_id": gateway.id,
                "body": "Your car is ready",
            }
        )
        with patch("requests.post", mock or MagicMock()) as post_mock:
            if not mock:
                response = MagicMock()
                response.json.return_value = {"sid": "SMoutbound1"}
                post_mock.return_value = response
            composer.action_send_twilio()
        channel = partner._twilio_get_channel("mobile", gateway)
        return post_mock, channel

    def test_send_from_number(self):
        post_mock, channel = self._send_via_composer()
        post_mock.assert_called_once()
        # From number is used as the sender.
        self.assertEqual(post_mock.call_args.kwargs["data"]["From"], "+15550000000")
        self.assertEqual(
            post_mock.call_args.kwargs["data"]["To"], self.customer_number
        )
        notification = channel.message_ids.notification_ids.filtered(
            lambda n: n.notification_type == "gateway"
        )
        self.assertEqual(notification.gateway_message_id, "SMoutbound1")
        self.assertEqual(notification.notification_status, "sent")

    def test_send_via_messaging_service(self):
        gateway = self.env["mail.gateway"].create(
            {
                "name": "Twilio MG",
                "gateway_type": "twilio",
                "token": "ACyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
                "webhook_secret": "auth-token-2",
                "twilio_messaging_service_sid": "MGxxxxxxxxxxxx",
                "webhook_key": "twilio_hook_mg",
                "member_ids": [(4, self.env.user.id)],
            }
        )
        gateway.integrated_webhook_state = "integrated"
        post_mock, _channel = self._send_via_composer(gateway=gateway)
        data = post_mock.call_args.kwargs["data"]
        self.assertEqual(data["MessagingServiceSid"], "MGxxxxxxxxxxxx")
        self.assertNotIn("From", data)

    @mute_logger(MODEL_LOGGER)
    def test_send_error_sets_exception(self):
        post_mock = MagicMock(side_effect=Exception("boom"))
        _post_mock, channel = self._send_via_composer(mock=post_mock)
        notification = channel.message_ids.notification_ids
        self.assertEqual(notification.notification_status, "exception")

    def test_status_callback_marks_failure(self):
        # First send so a notification with a known SID exists.
        response = MagicMock()
        response.json.return_value = {"sid": "SMtrack"}
        _post_mock, channel = self._send_via_composer(
            mock=MagicMock(return_value=response)
        )
        self.assertEqual(
            channel.message_ids.notification_ids.gateway_message_id, "SMtrack"
        )
        # Then a delivery-failure status callback.
        self._post(
            {
                "MessageSid": "SMtrack",
                "MessageStatus": "failed",
                "ErrorCode": "30008",
                "To": self.customer_number,
                "From": "+15550000000",
            }
        )
        notification = channel.message_ids.notification_ids
        self.assertEqual(notification.notification_status, "exception")
        self.assertIn("30008", notification.failure_reason)

    def test_server_action(self):
        partner = self.env["res.partner"].create(
            {"name": "Auto", "mobile": self.customer_number}
        )
        action = self.env["ir.actions.server"].create(
            {
                "name": "Text customer",
                "state": "twilio",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "twilio_gateway_id": self.gateway.id,
                "twilio_number_field": "mobile",
                "twilio_body": "Hello {{ object.name }}",
            }
        )
        response = MagicMock()
        response.json.return_value = {"sid": "SMaction"}
        with patch("requests.post", return_value=response) as post_mock:
            action.with_context(
                active_ids=[partner.id], active_id=partner.id
            ).run()
        post_mock.assert_called()
        channel = partner._twilio_get_channel("mobile", self.gateway)
        self.assertIn("Hello Auto", channel.message_ids.body)

    # ------------------------------------------------------------------
    # Webhook registration
    # ------------------------------------------------------------------
    def test_webhook_management(self):
        gateway = self.env["mail.gateway"].create(
            {
                "name": "Twilio Reg",
                "gateway_type": "twilio",
                "token": "ACzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
                "webhook_secret": "auth-token-3",
                "twilio_from_number": "+15551112222",
                "webhook_key": "twilio_hook_reg",
                "member_ids": [(4, self.env.user.id)],
            }
        )
        self.assertTrue(gateway.can_set_webhook)
        lookup = MagicMock()
        lookup.json.return_value = {"incoming_phone_numbers": [{"sid": "PN123"}]}
        lookup.raise_for_status.return_value = None
        with (
            patch("requests.get", return_value=lookup),
            patch("requests.post", return_value=MagicMock()) as post_mock,
        ):
            gateway.set_webhook()
            self.assertEqual(gateway.integrated_webhook_state, "integrated")
            # SmsUrl was set on the resolved IncomingPhoneNumber.
            self.assertTrue(
                any(
                    "IncomingPhoneNumbers/PN123" in call.args[0]
                    for call in post_mock.mock_calls
                    if call.args
                )
            )
            gateway.remove_webhook()
        self.assertFalse(gateway.integrated_webhook_state)
