# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models


class AIProvider(models.Model):
    _inherit = 'muk_ai.provider'

    cloudflare_account_id = fields.Char(
        string='Account ID',
        help='Cloudflare account id (Account Home, right-hand sidebar). '
        'Used to build the Workers AI endpoint and to look up the '
        'account model catalog - no need to enter a URL by hand.',
        groups='base.group_system',
    )

    # Overridden to derive its value for a Cloudflare provider instead of
    # asking for it directly. The base field is a plain Char, but core's
    # own `_check_api_region` constraint requires it whenever api_region
    # is 'custom' (which it always is here, per `regions = (CUSTOM,)`) -
    # hiding it in the view alone would leave that constraint failing
    # with an empty value, so it has to actually be kept filled in.
    api_url = fields.Char(
        compute='_compute_cloudflare_api_url',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('name', 'cloudflare_account_id')
    def _compute_cloudflare_api_url(self):
        for record in self:
            if record.name == 'cloudflare':
                record.api_url = (
                    'https://api.cloudflare.com/client/v4/accounts/'
                    f'{record.cloudflare_account_id}/ai/v1'
                    if record.cloudflare_account_id
                    else False
                )
            else:
                # Not this provider: leave whatever value it already has
                # (or was just given in the same create/write) alone.
                record.api_url = record.api_url

    cloudflare_gateway_id = fields.Char(
        string='Gateway ID',
        help='ID of a Cloudflare AI Gateway to route requests through '
        '(Account Home > AI Gateway). Sent as the cf-aig-gateway-id '
        'header so usage is tracked/billed under that gateway. Leave '
        'empty to call Workers AI directly, with no gateway.',
        groups='base.group_system',
    )

    cloudflare_api_token = fields.Char(
        string='API Token',
        help='Cloudflare API token with Workers AI permissions. Used '
        'in place of the generic API Key field above, which this '
        'provider does not use.',
        groups='base.group_system',
    )

    def action_fetch_cloudflare_models(self) -> dict:
        """Populate this provider's model catalog from Cloudflare's own
        list of models available to the configured account, creating or
        updating muk_ai.model records. Pricing always needs a manual
        pass afterwards - see CloudflareProvider.list_models().
        """
        self.ensure_one()
        model_vals_list = self._get_client().list_models()
        model_env = self.env['muk_ai.model']
        created = updated = 0
        for model_vals in model_vals_list:
            existing = model_env.search(
                [
                    ('provider_id', '=', self.id),
                    ('technical_name', '=', model_vals['technical_name']),
                ],
                limit=1,
            )
            if existing:
                existing.write(model_vals)
                updated += 1
            else:
                model_env.create({**model_vals, 'provider_id': self.id})
                created += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('AI Provider'),
                'message': _(
                    '%(created)s model(s) added, %(updated)s updated. '
                    'Pricing on each defaults to 0 - review it before '
                    'relying on cost tracking.',
                    created=created,
                    updated=updated,
                ),
                'sticky': False,
            },
        }
