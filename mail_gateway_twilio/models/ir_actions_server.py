# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, exceptions, fields, models


class IrServerAction(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[("twilio", "Twilio SMS")],
        ondelete={"twilio": "cascade"},
    )
    twilio_gateway_id = fields.Many2one(
        comodel_name="mail.gateway", domain=[("gateway_type", "=", "twilio")]
    )
    twilio_partner = fields.Char(
        string="Partner Expression",
        help="Optional inline expression returning the recipient partner id "
        "(e.g. object.partner_id.id). Defaults to the record's partner.",
    )
    twilio_number_field = fields.Char(
        string="Number Field",
        default="mobile",
        help="Field on the partner holding the phone number to text.",
    )
    twilio_body = fields.Text(
        string="SMS Body",
        help="Message body. Supports inline placeholders, e.g. {{ object.name }}.",
    )

    @api.depends("state")
    def _compute_available_model_ids(self):
        gateway_based = self.filtered(lambda action: action.state == "twilio")
        if gateway_based:
            mail_models = self.env["ir.model"].search(
                [("is_mail_thread", "=", True), ("transient", "=", False)]
            )
            gateway_based.available_model_ids = mail_models.ids
        return super(
            IrServerAction, self - gateway_based
        )._compute_available_model_ids()

    @api.constrains("state", "model_id")
    def _check_twilio_model_coherency(self):
        for action in self:
            if action.state == "twilio" and (
                action.model_id.transient or not action.model_id.is_mail_thread
            ):
                raise exceptions.ValidationError(
                    self.env._(
                        "Sending a Twilio SMS can only be done on a non transient "
                        "mail.thread model"
                    )
                )

    def _run_action_twilio_multi(self, eval_context=None):
        # Called by ir.actions~_get_runner() using the state naming convention.
        context = self.env.context
        if (
            not self.twilio_gateway_id
            or not self.twilio_body
            or (not context.get("active_ids") and not context.get("active_id"))
            or self._is_recompute()
        ):
            return False
        res_ids = context.get("active_ids", [context.get("active_id")])
        render = self.env["mail.render.mixin"]._render_template
        for record in self.env[self.model_id.model].browse(res_ids):
            if self.twilio_partner:
                rendered = render(self.twilio_partner, record._name, [record.id])
                partner = self.env["res.partner"].browse(int(rendered[record.id]))
            else:
                partner = record._twilio_get_partner()
            if not partner:
                continue
            channel = partner._twilio_get_channel(
                self.twilio_number_field or "mobile", self.twilio_gateway_id
            )
            body = render(self.twilio_body, record._name, [record.id])[record.id]
            channel.message_post(
                body=body,
                subtype_xmlid="mail.mt_comment",
                message_type="comment",
            )
        return False
