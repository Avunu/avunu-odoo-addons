# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json
import logging

import werkzeug.urls
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.auth_oauth.controllers.main import OAuthController

_logger = logging.getLogger(__name__)


class ShopfloorOAuthComplete(http.Controller):
    @http.route(
        "/shopfloor/oauth/<string:tech_name>/complete",
        type="http",
        auth="user",
    )
    def complete(self, tech_name, **kw):
        """Where an oauth-flavored app's `state.r` points (see
        `models/shopfloor_app.py._rewrite_oauth_link()`). Runs as whichever
        technician Odoo's own `/auth_oauth/signin` controller just
        authenticated (core `auth_oauth`'s existing session-creation flow,
        untouched) - resolves/mints their API key and redirects to
        `<app url>#apikey=<key>`, a URL fragment (never a query param) so
        the key never lands in server access logs or a `Referer` header.
        On denial, redirects to `#oauth_error=<code>` instead.
        """
        app = (
            request.env["shopfloor.app"]
            .sudo()
            .search(
                [("tech_name", "=", tech_name), ("auth_type", "=", "oauth")],
                limit=1,
            )
        )
        if not app:
            raise NotFound()
        return request.redirect(app.url + "#" + self._fragment_for(app))

    def _fragment_for(self, app):
        key = app.sudo()._get_or_create_oauth_api_key(request.env.user)
        if not key:
            _logger.warning(
                "shopfloor oauth: %s authenticated for app %s but no "
                "usable API key was found or provisioned; denying.",
                request.env.user.login,
                app.tech_name,
            )
            return "oauth_error=no_key"
        return "apikey=" + werkzeug.urls.url_quote(key.key)


class ShopfloorOAuthSignin(OAuthController):
    @http.route(
        "/auth_oauth/signin",
        type="http",
        auth="none",
        csrf=False,
        readonly=False,
    )
    def signin(self, **kw):
        """Only override needed for Apple: Google's `id_token_code` flow
        returns via a normal GET redirect (`?code=...&state=...`), which
        is unaffected by Odoo's CSRF check (GET is CSRF-exempt by
        default). Apple's mandatory `response_mode=form_post`
        (`shopfloor_app.py._oauth_provider_needs_form_post()`) delivers
        the callback as a cross-site POST with no Odoo `csrf_token`
        attached, which Odoo's default `csrf=True` on `type='http'`
        routes would reject with a 400. This endpoint's actual security
        boundary is JWKS signature verification of the `id_token` plus
        PKCE - both untouched by this override - not Odoo's ambient-
        session CSRF token, which was never a meaningful defense for a
        third-party redirect callback in the first place.

        Bundled fix while overriding this route anyway: core's failure
        path hardcodes a redirect to `/web/login?oauth_error=N`, the
        wrong screen for a mobile app. When this login attempt was
        shopfloor-initiated (`state.r` points at our own `/shopfloor/
        oauth/<tech_name>/complete`), rewrite that redirect back to the
        shopfloor app's own URL with the same `#oauth_error=` convention
        instead - without duplicating core's whole signin() body, which
        catches and redirects its exceptions internally rather than
        raising them back out to us.
        """
        resp = super().signin(**kw)
        return self._redirect_failure_to_shopfloor(resp, kw)

    def _redirect_failure_to_shopfloor(self, resp, kw):
        location = getattr(resp, "location", "") or ""
        if "/web/login" not in location or "oauth_error=" not in location:
            return resp
        redirect_target = self._shopfloor_complete_url(kw)
        if not redirect_target:
            return resp
        error_code = werkzeug.urls.url_decode(location.split("?", 1)[-1]).get(
            "oauth_error", "2"
        )
        resp.location = redirect_target + "#oauth_error=" + error_code
        resp.autocorrect_location_header = False
        return resp

    def _shopfloor_complete_url(self, kw):
        try:
            state = json.loads(kw.get("state") or "{}")
        except ValueError:
            return None
        redirect = state.get("r")
        if not redirect:
            return None
        redirect = werkzeug.urls.url_unquote_plus(redirect)
        if "/shopfloor/oauth/" not in redirect:
            return None
        return redirect
