# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["mail.thread.phone", "res.partner"]

    def _twilio_get_partner(self):
        return self

    def _phone_get_number_fields(self):
        """Fields used to resolve the number to text / match inbound senders."""
        result = set(super()._phone_get_number_fields())
        result.add("mobile")
        result.add("phone")
        return list(result)
