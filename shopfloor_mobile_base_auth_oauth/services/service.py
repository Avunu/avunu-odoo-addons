# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from werkzeug.exceptions import Forbidden

from odoo.addons.component.core import AbstractComponent

_logger = logging.getLogger(__name__)


class BaseShopfloorService(AbstractComponent):
    _inherit = "base.shopfloor.service"

    def _validate_request(self, request):
        # `shopfloor_mobile_base_auth_api_key`'s own `_validate_request` is
        # gated on the literal string `self.collection.auth_type ==
        # "api_key"`, so it silently no-ops for an oauth-flavored app - the
        # request's `auth_api_key_id` (set by `ir_http._auth_method_oauth`,
        # aliased straight to `_auth_method_api_key`) would never be
        # checked against this app's own allow-list. We can't edit that
        # vendored file, so re-run the same check here for "oauth", reusing
        # the identical `_allowed_api_key_ids()` helper the sibling module
        # defines on `shopfloor.app` (an oauth-flavored app's own
        # `auth_api_key_group_ids` - the same field that field's `oauth_
        # api_key_group_id` must be a member of for a minted key to pass
        # this check; see shopfloor_app.py).
        super()._validate_request(request)
        if self.collection.auth_type == "oauth":
            if (
                self.request.auth_api_key_id
                not in self.collection.sudo()._allowed_api_key_ids()
            ):
                _logger.error(
                    "API key not allowed on app '%s'", self.collection.tech_name
                )
                raise Forbidden()
