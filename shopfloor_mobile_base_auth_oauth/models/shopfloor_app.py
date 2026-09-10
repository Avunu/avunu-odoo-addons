# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json
import logging
import secrets

from psycopg2 import IntegrityError
from werkzeug.urls import url_decode, url_encode, url_parse, url_quote_plus

from odoo import fields, models

from odoo.addons.auth_oidc.controllers.main import OpenIDLogin

_logger = logging.getLogger(__name__)


class ShopfloorApp(models.Model):
    _inherit = "shopfloor.app"

    def _selection_auth_type(self):
        return super()._selection_auth_type() + [
            ("oauth", "Social login (Google/Apple)")
        ]

    oauth_api_key_group_id = fields.Many2one(
        "auth.api.key.group",
        string="Group for auto-provisioned keys",
        help="Where an auto-minted key gets filed when 'Auto-provision API "
        "key' below is on. Must also be one of this app's own 'Allowed API "
        "key groups' (from the API key auth module) - otherwise a freshly "
        "minted key would still fail this app's own allow-list check on "
        "the very next request.",
    )
    oauth_allow_signup = fields.Boolean(
        string="Allow sign-up",
        help="Off (the default): a Google/Apple identity with no matching "
        "Odoo user is rejected - admins keep creating technician accounts "
        "the way they do today. On: Odoo's own auth_oauth sign-up flow "
        "runs instead, which creates a NEW res.users record rather than "
        "linking to any existing one with a matching email - only turn "
        "this on if that is actually what you want.",
    )
    oauth_auto_provision_key = fields.Boolean(
        string="Auto-provision API key",
        help="Off (the default): a technician who authenticates but has "
        "no existing auth.api.key in this app's allowed groups is denied "
        "and told to ask an admin, matching today's one-key-per-"
        "technician-by-hand policy. On: a key is minted automatically on "
        "first login and filed under 'Group for auto-provisioned keys' "
        "above (required in that case).",
    )

    def _make_app_info(self, demo=False):
        info = super()._make_app_info(demo=demo)
        if self.auth_type == "oauth":
            info["oauth_providers"] = self._make_oauth_providers()
        return info

    def _make_oauth_providers(self):
        """Build the provider list for this app's pre-login page.

        Delegates to OCA `auth_oidc`'s own `OpenIDLogin().list_providers()`
        so PKCE, nonce, and `response_type` construction stay exactly in
        sync with what that module already does for `/web/login` - then
        keeps only the subset of each provider dict that's safe to inline,
        unauthenticated, into the page's HTML (`search_read()` with no
        `fields` argument, which `list_providers()` uses, returns *every*
        field, `client_secret` and PKCE's `code_verifier` included; those
        must never reach the frontend).
        """
        self.ensure_one()
        return [
            self._rewrite_oauth_provider(provider)
            for provider in OpenIDLogin().list_providers()
        ]

    def _rewrite_oauth_provider(self, provider):
        self.ensure_one()
        return {
            "id": provider["id"],
            "name": provider["name"],
            "body": provider["body"],
            "css_class": provider["css_class"],
            "auth_link": self._rewrite_oauth_link(provider),
        }

    def _rewrite_oauth_link(self, provider):
        """Patch one provider's `auth_link` for a kiosk-less mobile app.

        Two changes on top of what `list_providers()` already built:
        redirect `state.r` to this app's own completion URL instead of
        Odoo's default `/web`, and - unless sign-up is allowed - inject
        `state.c = {"no_user_creation": True}`, the same context flag
        core `auth_oauth` already understands, so a Google/Apple identity
        with no matching `res.users` is rejected rather than auto-signed-up
        (see `oauth_allow_signup`'s help text for what "matching" means in
        practice).
        """
        self.ensure_one()
        parsed = url_parse(provider["auth_link"])
        params = url_decode(parsed.query)
        state = json.loads(params["state"])
        complete_url = "{}/shopfloor/oauth/{}/complete".format(
            self.get_base_url(), self.tech_name
        )
        # Matches core `OAuthLogin.get_state()`'s own convention exactly:
        # `state['r']` holds the url_quote_plus'd redirect target, later
        # read back with `url_unquote_plus` by `/auth_oauth/signin`.
        state["r"] = url_quote_plus(complete_url)
        if not self.oauth_allow_signup:
            state["c"] = {"no_user_creation": True}
        params["state"] = json.dumps(state)
        if self._oauth_provider_needs_form_post(provider):
            params["response_mode"] = "form_post"
        return parsed.replace(query=url_encode(params)).to_url()

    def _oauth_provider_needs_form_post(self, provider):
        """Whether this provider's callback must arrive as a POST.

        Apple mandates `response_mode=form_post` for any flow that
        requests an `id_token` - neither of `auth_oidc`'s flow
        implementations set it on their own. Matched by the auth
        endpoint's host rather than a hardcoded provider xmlid, so it
        still applies if the seed record gets renamed or duplicated. See
        `controllers/main.py.ShopfloorOAuthSignin` for why a form-post
        callback also needs `csrf=False` on `/auth_oauth/signin`.
        """
        return "appleid.apple.com" in (provider.get("auth_endpoint") or "")

    def _get_or_create_oauth_api_key(self, user):
        """Resolve `user`'s API key for this (oauth-flavored) app.

        Looks up an existing key among this app's allowed groups first -
        found, it's returned as-is so repeat logins reuse the same key
        rather than minting duplicates. Only mints a new one, filed under
        `oauth_api_key_group_id`, when `oauth_auto_provision_key` is on;
        otherwise returns an empty recordset and leaves denying the login
        to the caller (see `controllers/main.py.ShopfloorOAuthComplete`).
        """
        self.ensure_one()
        key = self._find_oauth_api_key(user)
        if key or not self.oauth_auto_provision_key:
            return key
        if not self.oauth_api_key_group_id:
            _logger.warning(
                "shopfloor.app %s (%s) has oauth_auto_provision_key set "
                "but no oauth_api_key_group_id; %s will be denied instead "
                "of provisioned a key.",
                self.tech_name,
                self.id,
                user.login,
            )
            return key
        return self._create_oauth_api_key(user)

    def _find_oauth_api_key(self, user):
        self.ensure_one()
        return (
            self.env["auth.api.key"]
            .sudo()
            .search(
                [
                    ("id", "in", self.sudo()._allowed_api_key_ids()),
                    ("user_id", "=", user.id),
                ],
                limit=1,
            )
        )

    def _create_oauth_api_key(self, user):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                key = (
                    self.env["auth.api.key"]
                    .sudo()
                    .create(
                        {
                            "name": f"{self.tech_name}:{user.login} (oauth)",
                            "user_id": user.id,
                            "key": secrets.token_hex(32),
                        }
                    )
                )
                self.sudo().oauth_api_key_group_id.write(
                    {"auth_api_key_ids": [(4, key.id)]}
                )
        except IntegrityError:
            # Two concurrent first-logins for the same technician on the
            # same app raced to mint a key with the same `name`; the
            # loser's insert rolled back to the savepoint above - the
            # winner's key is now findable by the plain search this
            # method's caller already did.
            key = self._find_oauth_api_key(user)
        return key
