# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class MailGateway(models.Model):
    _inherit = "mail.gateway"

    gateway_type = fields.Selection(
        selection_add=[("twilio", "Twilio")], ondelete={"twilio": "cascade"}
    )
    # Credential mapping (documented on the gateway form):
    #   * base ``token``          -> Twilio Account SID (HTTP-basic username)
    #   * base ``webhook_secret`` -> Twilio Auth Token  (HTTP-basic password
    #     and the key used to validate the X-Twilio-Signature on inbound
    #     requests; it is the only secret exposed to the controller via
    #     ``_get_gateway_data``).
    twilio_from_number = fields.Char(
        string="Twilio From Number",
        help="Sender phone number in E.164 format (e.g. +15551234567). "
        "Ignored when a Messaging Service SID is set.",
    )
    twilio_messaging_service_sid = fields.Char(
        string="Messaging Service SID",
        help="Optional Twilio Messaging Service SID (MG...). When set, it is "
        "used as the sender instead of the From number (recommended for US "
        "A2P 10DLC).",
    )
