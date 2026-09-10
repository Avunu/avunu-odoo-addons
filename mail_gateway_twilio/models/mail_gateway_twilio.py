# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import base64
import hashlib
import hmac
import logging
import mimetypes
import traceback
from io import StringIO

import requests

from odoo import models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import html2plaintext

from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
TWILIO_MESSAGING_BASE = "https://messaging.twilio.com/v1"


class MailGatewayTwilioService(models.AbstractModel):
    _inherit = "mail.gateway.abstract"
    _name = "mail.gateway.twilio"
    _description = "Twilio Gateway services"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _twilio_webhook_url(self, gateway):
        """Public URL Twilio posts to. Built from web.base.url + the framework
        path so it is deterministic (used both to register the webhook and to
        recompute the signed URL); it must match the externally reachable URL,
        so web.base.url has to be the public HTTPS address (enable proxy_mode).
        """
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        return "{}/gateway/{}/{}/update".format(
            base_url, gateway.gateway_type, gateway.webhook_key
        )

    def _twilio_auth(self, gateway):
        return (gateway.token, gateway.webhook_secret)

    def _get_proxies(self):
        # Hook to inject requests proxies if needed. By default does nothing.
        return {}

    # ------------------------------------------------------------------
    # Inbound verification
    # ------------------------------------------------------------------
    def _verify_update(self, bot_data, kwargs):
        """Validate Twilio's ``X-Twilio-Signature``.

        Twilio signs base64(HMAC-SHA1(auth_token, url + sorted "keyvalue"
        concatenation of the POST params)). ``webhook_secret`` holds the auth
        token (it is the only secret present in ``bot_data``).
        """
        signature = request.httprequest.headers.get("X-Twilio-Signature")
        secret = bot_data.get("webhook_secret")
        if not signature or not secret:
            return False
        gateway = self.env["mail.gateway"].browse(bot_data["id"])
        url = self._twilio_webhook_url(gateway)
        data = url + "".join(f"{key}{value}" for key, value in sorted(kwargs.items()))
        computed = base64.b64encode(
            hmac.new(secret.encode(), data.encode(), hashlib.sha1).digest()
        ).decode()
        return hmac.compare_digest(computed, signature)

    # ------------------------------------------------------------------
    # Webhook registration (auto, with graceful fallback to manual)
    # ------------------------------------------------------------------
    def _set_webhook(self, gateway):
        try:
            self._twilio_register_webhook(gateway, self._twilio_webhook_url(gateway))
        except Exception as exc:
            _logger.warning(
                "Twilio webhook auto-registration failed for gateway %s: %s. "
                "Configure the inbound URL manually in the Twilio console.",
                gateway.name,
                exc,
            )
        gateway.integrated_webhook_state = "integrated"

    def _remove_webhook(self, gateway):
        try:
            self._twilio_register_webhook(gateway, "")
        except Exception as exc:
            _logger.warning(
                "Twilio webhook removal failed for gateway %s: %s", gateway.name, exc
            )
        return super()._remove_webhook(gateway)

    def _twilio_register_webhook(self, gateway, webhook_url):
        auth = self._twilio_auth(gateway)
        proxies = self._get_proxies()
        if gateway.twilio_messaging_service_sid:
            response = requests.post(
                "{}/Services/{}".format(
                    TWILIO_MESSAGING_BASE, gateway.twilio_messaging_service_sid
                ),
                data={"InboundRequestUrl": webhook_url, "InboundMethod": "POST"},
                auth=auth,
                timeout=10,
                proxies=proxies,
            )
            response.raise_for_status()
        elif gateway.twilio_from_number:
            lookup = requests.get(
                "{}/Accounts/{}/IncomingPhoneNumbers.json".format(
                    TWILIO_API_BASE, gateway.token
                ),
                params={"PhoneNumber": gateway.twilio_from_number},
                auth=auth,
                timeout=10,
                proxies=proxies,
            )
            lookup.raise_for_status()
            numbers = lookup.json().get("incoming_phone_numbers", [])
            if not numbers:
                raise UserError(
                    self.env._(
                        "Twilio number %s was not found on the account.",
                        gateway.twilio_from_number,
                    )
                )
            response = requests.post(
                "{}/Accounts/{}/IncomingPhoneNumbers/{}.json".format(
                    TWILIO_API_BASE, gateway.token, numbers[0]["sid"]
                ),
                data={"SmsUrl": webhook_url, "SmsMethod": "POST"},
                auth=auth,
                timeout=10,
                proxies=proxies,
            )
            response.raise_for_status()

    # ------------------------------------------------------------------
    # Inbound processing
    # ------------------------------------------------------------------
    def _receive_update(self, gateway, update):
        if not update:
            return
        # Inbound messages carry a Body and/or media. Status callbacks for our
        # own outbound messages carry MessageStatus but no Body. Check the
        # message shape first because inbound also includes SmsStatus=received.
        if update.get("Body") or int(update.get("NumMedia") or 0):
            number = update.get("From")
            chat = (
                self._get_channel(gateway, number, update, force_create=True)
                if number
                else False
            )
            if chat:
                self._process_update(chat, update)
        elif update.get("MessageStatus") or update.get("SmsStatus"):
            self._process_update_status(gateway, update)

    def _process_update(self, chat, update):
        chat.ensure_one()
        gateway = chat.gateway_id
        body = update.get("Body") or ""
        attachments = []
        num_media = int(update.get("NumMedia") or 0)
        for index in range(num_media):
            media_url = update.get(f"MediaUrl{index}")
            if not media_url:
                continue
            content_type = (update.get(f"MediaContentType{index}") or "").split(";")[0]
            media_request = requests.get(
                media_url,
                auth=self._twilio_auth(gateway),
                timeout=10,
                proxies=self._get_proxies(),
            )
            media_request.raise_for_status()
            attachment_info = {}
            if content_type.startswith("audio/"):
                # Tell discuss to treat this attachment as a voice note.
                attachment_info["voice"] = True
            extension = mimetypes.guess_extension(content_type) or ""
            message_sid = update.get("MessageSid") or "media"
            filename = (
                "{}{}".format(message_sid, extension)
                if num_media == 1
                else "{}-{}{}".format(message_sid, index, extension)
            )
            attachments.append((filename, media_request.content, attachment_info))
        if not body and not attachments:
            return
        author = self._get_author(gateway, update)
        if author and author._name == "mail.guest":
            chat = chat.with_user(self.env.ref("base.public_user").id).with_context(
                guest=author
            )
        new_message = chat.sudo().message_post(
            body=body,
            author_id=author and author._name == "res.partner" and author.id,
            gateway_type="twilio",
            subtype_xmlid="mail.mt_comment",
            message_type="comment",
            attachments=attachments,
        )
        self._post_process_message(new_message, chat)

    def _process_update_status(self, gateway, update):
        message_sid = update.get("MessageSid") or update.get("SmsSid")
        status = update.get("MessageStatus") or update.get("SmsStatus")
        if not message_sid:
            return
        notification = (
            self.env["mail.notification"]
            .sudo()
            .search(
                [
                    ("gateway_message_id", "=", message_sid),
                    ("gateway_channel_id.gateway_id", "=", gateway.id),
                ],
                limit=1,
            )
        )
        if not notification:
            return
        if status in ("failed", "undelivered"):
            error_code = update.get("ErrorCode")
            error_message = update.get("ErrorMessage") or ""
            reason = (
                "[{}] {}".format(error_code, error_message)
                if error_code
                else (error_message or status)
            )
            notification.write(
                {
                    "notification_status": "exception",
                    "failure_type": "unknown",
                    "failure_reason": reason,
                }
            )
            notification.mail_message_id._notify_message_notification_update()
        elif status == "delivered":
            notification.write(
                {"notification_status": "sent", "failure_reason": False}
            )

    # ------------------------------------------------------------------
    # Author / channel resolution
    # ------------------------------------------------------------------
    def _get_channel_vals(self, gateway, token, update):
        result = super()._get_channel_vals(gateway, token, update)
        result["name"] = update.get("ProfileName") or token
        return result

    def _get_author(self, gateway, update):
        author_id = update.get("From")
        if not author_id:
            return False
        author_id = str(author_id)
        gateway_partner = self.env["res.partner.gateway.channel"].search(
            [
                ("gateway_id", "=", gateway.id),
                ("gateway_token", "=", author_id),
            ]
        )
        if gateway_partner:
            return gateway_partner.partner_id
        # Twilio's From is already E.164 with a leading '+', matching
        # res.partner.phone_sanitized directly (no prefixing needed).
        partner = self.env["res.partner"].search(
            [("phone_sanitized", "=", author_id)], limit=1
        )
        if partner:
            self.env["res.partner.gateway.channel"].create(
                {
                    "name": gateway.name,
                    "partner_id": partner.id,
                    "gateway_id": gateway.id,
                    "gateway_token": author_id,
                }
            )
            return partner
        guest = self.env["mail.guest"].search(
            [
                ("gateway_id", "=", gateway.id),
                ("gateway_token", "=", author_id),
            ]
        )
        if guest:
            return guest
        return self.env["mail.guest"].create(
            self._get_author_vals(gateway, author_id, update)
        )

    def _get_author_vals(self, gateway, author_id, update):
        return {
            "name": update.get("ProfileName") or str(author_id),
            "gateway_id": gateway.id,
            "gateway_token": str(author_id),
        }

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------
    def _send(
        self,
        gateway,
        record,
        auto_commit=False,
        raise_exception=False,
        parse_mode=False,
    ):
        message = False
        try:
            body = self._get_message_body(record)
            body = html2plaintext(body) if body else ""
            data = {
                "To": record.gateway_channel_id.gateway_channel_token,
                "Body": body,
                "StatusCallback": self._twilio_webhook_url(gateway),
            }
            if gateway.twilio_messaging_service_sid:
                data["MessagingServiceSid"] = gateway.twilio_messaging_service_sid
            else:
                data["From"] = gateway.twilio_from_number
            response = requests.post(
                "{}/Accounts/{}/Messages.json".format(TWILIO_API_BASE, gateway.token),
                data=data,
                auth=self._twilio_auth(gateway),
                timeout=10,
                proxies=self._get_proxies(),
            )
            response.raise_for_status()
            message = response.json()
        except Exception as exc:
            buff = StringIO()
            traceback.print_exc(file=buff)
            _logger.error(buff.getvalue())
            if raise_exception:
                raise MailDeliveryException(
                    self.env._("Unable to send the Twilio SMS")
                ) from exc
            _logger.warning("Issue sending message with id %s: %s", record.id, exc)
            record.sudo().write(
                {
                    "notification_status": "exception",
                    "failure_reason": str(exc),
                    "failure_type": "unknown",
                }
            )
        if message:
            record.sudo().write(
                {
                    "notification_status": "sent",
                    "failure_reason": False,
                    "gateway_message_id": message.get("sid"),
                }
            )
        if auto_commit is True:
            # pylint: disable=invalid-commit
            self.env.cr.commit()
