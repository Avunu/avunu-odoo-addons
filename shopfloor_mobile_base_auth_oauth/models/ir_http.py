# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _auth_method_oauth(cls):
        """Alias for `_auth_method_api_key` (from `auth_api_key`, a hard
        dependency of `shopfloor_mobile_base_auth_api_key`, itself a hard
        dependency of this module).

        `shopfloor.app._prepare_endpoint_vals()` writes `auth_type=self.
        auth_type` onto every REST route the app publishes, and Odoo's
        router resolves that through `ir.http._auth_method_<value>`
        (`endpoint.route.handler._make_controller_rule()` passes
        `auth=self.auth_type` straight to werkzeug). Without this alias,
        setting a `shopfloor.app`'s `auth_type` to `"oauth"` renders the
        *login page* fine but the very next API call (`user_config`) 500s
        with an unhandled `AttributeError`, because nothing has ever taught
        Odoo's router what `"oauth"` means as a request-auth mechanism.

        This is correct as a plain alias, not a stub: once OAuth login has
        completed, every ongoing request from an oauth-flavored app carries
        the exact same `API-KEY` header as an api_key-flavored app (see
        `models/shopfloor_app.py._get_or_create_oauth_api_key()` and
        `static/src/login.esm.js`, which reuses the api_key auth handler
        verbatim) - so authenticating it the same way is exactly right.
        """
        return cls._auth_method_api_key()
