# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class MailGateway(models.Model):
    _inherit = "mail.gateway"

    is_sms_mirror_target = fields.Boolean(
        string="Mirror outbound SMS here",
        help="When set, outbound core-notification and SMS-Marketing messages "
        "sent from this gateway's company are mirrored into this gateway's "
        "per-contact threads, so a customer's replies thread together with the "
        "message they are answering. Use one target gateway per company.",
    )
