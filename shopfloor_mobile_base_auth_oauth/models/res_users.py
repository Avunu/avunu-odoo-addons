# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _generate_signup_values(self, provider, validation, params):
        """Pick up Apple's name/email, sent only on the very first
        authorization ever, as a POST body `user` field (JSON) - never in
        the `id_token` itself and never again on subsequent logins. This
        only matters if `oauth_allow_signup` is ever turned on for an app
        (see `shopfloor_app.py`). Mirrors the exact technique OCA's own
        `auth_oauth_login_field` module uses for a similar `login` claim.
        """
        res = super()._generate_signup_values(provider, validation, params)
        apple_user = params.get("user")
        if not apple_user:
            return res
        try:
            apple_user = json.loads(apple_user)
        except (TypeError, ValueError):
            _logger.warning(
                "Apple oauth: a 'user' param was present but not valid "
                "JSON; ignoring it for this signup's name/email."
            )
            return res
        name = apple_user.get("name") or {}
        full_name = " ".join(
            part for part in (name.get("firstName"), name.get("lastName")) if part
        )
        if full_name:
            res["name"] = full_name
        email = apple_user.get("email")
        if email:
            res["login"] = email
            res["email"] = email
        return res
