# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestSmsMirror(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gateway = cls.env["mail.gateway"].create(
            {
                "name": "Twilio",
                "gateway_type": "twilio",
                "token": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "webhook_secret": "auth-token",
                "twilio_from_number": "+15550000000",
                "webhook_key": "twilio_mirror_hook",
                "is_sms_mirror_target": True,
                "member_ids": [(4, cls.env.user.id)],
            }
        )
        cls.number = "+34699999999"
        cls.partner = cls.env["res.partner"].create(
            {"name": "Customer", "mobile": cls.number}
        )

    def _channel(self):
        return self.env["discuss.channel"].search(
            [("gateway_id", "=", self.gateway.id)]
        )

    def _make_sms(self, state="pending", body="Your invoice is ready"):
        return self.env["sms.sms"].create(
            {
                "number": self.number,
                "body": body,
                "partner_id": self.partner.id,
                "state": state,
            }
        )

    def test_mirror_sent_sms(self):
        sms = self._make_sms()
        sms._handle_call_result_hook([])
        channel = self._channel()
        self.assertTrue(channel, "A gateway channel should be created")
        self.assertEqual(channel.gateway_channel_token, self.number)
        self.assertIn("Your invoice is ready", channel.message_ids.body)

    def test_mirror_is_display_only_no_resend(self):
        """The mirrored message must not create a gateway notification
        (which would re-send via Twilio) nor a new sms.sms (no loop)."""
        sms = self._make_sms()
        sms_count_before = self.env["sms.sms"].search_count([])
        sms._handle_call_result_hook([])
        message = self._channel().message_ids
        self.assertFalse(
            message.notification_ids.filtered(
                lambda n: n.notification_type == "gateway"
            ),
            "Mirrored message must not trigger an outbound gateway send",
        )
        self.assertEqual(
            self.env["sms.sms"].search_count([]),
            sms_count_before,
            "Mirroring must not create additional sms.sms records",
        )

    def test_failed_sms_not_mirrored(self):
        sms = self._make_sms(state="error")
        sms._handle_call_result_hook([])
        self.assertFalse(self._channel())

    def test_mirror_skip_context(self):
        sms = self._make_sms()
        sms.with_context(mail_gateway_mirror_skip=True)._handle_call_result_hook([])
        self.assertFalse(self._channel())

    def test_no_gateway_no_crash(self):
        # With no Twilio gateway at all, resolution returns nothing and the
        # hook must be a safe no-op (no channel, no exception).
        self.env["mail.gateway"].search([("gateway_type", "=", "twilio")]).unlink()
        sms = self._make_sms()
        sms._handle_call_result_hook([])  # must not raise
        self.assertFalse(
            self.env["discuss.channel"].search([("channel_type", "=", "gateway")])
        )
