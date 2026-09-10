# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SmsSms(models.Model):
    _inherit = "sms.sms"

    def _resolve_mirror_gateway(self, sms):
        """Pick the Twilio gateway to mirror ``sms`` into (overridable hook).

        Order: a per-user gateway whose ``webhook_user_id`` is the SMS author
        (only possible for notification SMS, which carry a message/author);
        else the gateway flagged as the company's mirror target; else the sole
        Twilio gateway for the SMS company. Routing by the actual Twilio "From"
        number is not possible: it is chosen later (by destination country) and
        never stored.
        """
        Gateway = self.env["mail.gateway"].sudo()
        company = sms._get_sms_company()
        base_domain = [
            ("gateway_type", "=", "twilio"),
            ("company_id", "in", [company.id, False]),
        ]
        author = sms.mail_message_id.author_id
        users = author.user_ids if author else self.env["res.users"]
        if users:
            gateway = Gateway.search(
                base_domain + [("webhook_user_id", "in", users.ids)], limit=1
            )
            if gateway:
                return gateway
        gateway = Gateway.search(
            base_domain + [("is_sms_mirror_target", "=", True)], limit=1
        )
        return gateway or Gateway.search(base_domain, limit=1)

    def _handle_call_result_hook(self, results):
        res = super()._handle_call_result_hook(results)
        if self.env.context.get("mail_gateway_mirror_skip"):
            return res
        # Only successfully-submitted messages (pending == "Sent",
        # sent == "Delivered"); errors keep their own pipeline.
        for sms in self.filtered(
            lambda s: s.state in ("pending", "sent") and s.number
        ):
            try:
                self._mirror_sms_to_gateway(sms)
            except Exception as exc:  # never break the core SMS send
                _logger.warning(
                    "Failed to mirror SMS %s into a Twilio gateway thread: %s",
                    sms.id,
                    exc,
                )
        return res

    def _mirror_sms_to_gateway(self, sms):
        gateway = self._resolve_mirror_gateway(sms)
        if not gateway:
            return
        channel = self.env["mail.gateway.twilio"]._get_channel(
            gateway, sms.number, {"From": sms.number}, force_create=True
        )
        if not channel:
            return
        author = sms.mail_message_id.author_id
        if not author and "mailing_id" in sms._fields and sms.mailing_id:
            # Marketing SMS have no message/author: attribute to the mailing owner.
            author = sms.mailing_id.user_id.partner_id
        # no_gateway_notification=True -> display only, never re-sends via _send.
        channel.with_context(no_gateway_notification=True).sudo().message_post(
            body=sms.body or "",
            author_id=author.id if author else False,
            gateway_type="twilio",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
