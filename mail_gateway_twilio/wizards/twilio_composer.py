# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import UserError


class TwilioComposer(models.TransientModel):
    _name = "twilio.composer"
    _description = "Compose a Twilio SMS"

    res_model = fields.Char("Document Model Name")
    res_id = fields.Integer("Document ID")
    number_field_name = fields.Char(default="mobile")
    find_gateway = fields.Boolean()
    gateway_id = fields.Many2one(
        "mail.gateway",
        domain=[("gateway_type", "=", "twilio")],
        required=True,
    )
    body = fields.Text("Message", required=True)

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        if not result.get("res_model") and self.env.context.get("active_model"):
            result["res_model"] = self.env.context["active_model"]
        if not result.get("res_id") and self.env.context.get("active_id"):
            result["res_id"] = self.env.context["active_id"]
        gateways = self.env["mail.gateway"].search([("gateway_type", "=", "twilio")])
        result["find_gateway"] = len(gateways) != 1
        if len(gateways) == 1:
            result["gateway_id"] = gateways.id
        return result

    def _action_send_twilio(self):
        record = self.env[self.res_model].browse(self.res_id)
        if not record:
            return
        channel = record._twilio_get_channel(self.number_field_name, self.gateway_id)
        channel.message_post(
            body=self.body,
            subtype_xmlid="mail.mt_comment",
            message_type="comment",
        )

    def action_send_twilio(self):
        self.ensure_one()
        if not self.body:
            raise UserError(self.env._("Message body is required"))
        self._action_send_twilio()
        return False

    def action_view_twilio(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id)
        if not record:
            return False
        channel = record._twilio_get_channel(self.number_field_name, self.gateway_id)
        if channel:
            return {
                "type": "ir.actions.client",
                "tag": "mail.action_discuss",
                "params": {"active_id": f"{channel._name}_{channel.id}"},
            }
        return False
