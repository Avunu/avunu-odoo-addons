# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models
from odoo.exceptions import UserError


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _twilio_get_partner(self):
        if "partner_id" in self._fields:
            return self.partner_id
        return self.env["res.partner"]

    def _twilio_get_channel(self, field_name, gateway):
        """Find or create the gateway channel for this record's phone number.

        The token is E.164 with the leading ``+`` (kept, unlike WhatsApp), so it
        matches Twilio's inbound ``From`` and ``res.partner.phone_sanitized``.
        """
        number = self._phone_format(number=self[field_name])
        if not number:
            raise UserError(
                self.env._("The phone number could not be formatted to E.164.")
            )
        partner = self._twilio_get_partner()
        if partner and not self.env["res.partner.gateway.channel"].search(
            [
                ("partner_id", "=", partner.id),
                ("gateway_id", "=", gateway.id),
                ("gateway_token", "=", number),
            ]
        ):
            self.env["res.partner.gateway.channel"].create(
                {
                    "name": gateway.name,
                    "partner_id": partner.id,
                    "gateway_id": gateway.id,
                    "gateway_token": number,
                }
            )
        return self.env["mail.gateway.twilio"]._get_channel(
            gateway,
            number,
            {
                "From": number,
                "ProfileName": partner.display_name if partner else number,
            },
            force_create=True,
        )
