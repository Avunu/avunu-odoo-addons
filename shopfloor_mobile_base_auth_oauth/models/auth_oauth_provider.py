# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging
import time

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    from jose import jwt
except ImportError:  # pragma: no cover - auth_oidc's own hard dependency
    jwt = None

_logger = logging.getLogger(__name__)

# Apple's own maximum lifetime for this JWT's `exp` claim (verified against
# Apple/Okta documentation).
APPLE_CLIENT_SECRET_MAX_AGE = 60 * 60 * 24 * 180  # 180 days


class AuthOauthProvider(models.Model):
    _name = "auth.oauth.provider"
    _inherit = ["auth.oauth.provider", "server.env.mixin"]

    apple_team_id = fields.Char(
        string="Apple Team ID",
        help="From the Apple Developer portal's Membership page. Required, "
        "together with the two fields below, to mint Apple's client "
        "secret automatically (Apple doesn't issue a static one the way "
        "Google does).",
    )
    apple_key_id = fields.Char(
        string="Apple Key ID",
        help="The Key ID of the 'Sign in with Apple' private key (.p8) "
        "generated in the Apple Developer portal's Keys section.",
    )
    apple_private_key = fields.Text(
        string="Apple Private Key",
        help="The contents of the .p8 private key file downloaded when "
        "the key above was generated. A real secret at rest - set this "
        "via a server_environment config file where the deployment "
        "supports it, rather than here directly (see this module's "
        "README).",
    )

    @property
    def _server_env_fields(self):
        base_fields = super()._server_env_fields
        return {"apple_private_key": {}, **base_fields}

    def _mint_apple_client_secret(self):
        """Build Apple's non-static `client_secret` as a signed JWT.

        Apple doesn't issue a static client_secret the way Google does;
        instead you mint one yourself, valid for at most 180 days.
        `client_secret` is otherwise a plain Char used directly for HTTP
        Basic auth on `auth_oidc`'s token exchange
        (`res_users._auth_oauth_get_tokens_auth_code_flow`), so minting
        the JWT and writing it there is the only Apple-specific piece.
        """
        self.ensure_one()
        if jwt is None:
            raise UserError(
                _("python-jose is not installed; cannot mint an Apple "
                  "client secret.")
            )
        now = int(time.time())
        claims = {
            "iss": self.apple_team_id,
            "iat": now,
            "exp": now + APPLE_CLIENT_SECRET_MAX_AGE,
            "aud": "https://appleid.apple.com",
            "sub": self.client_id,
        }
        return jwt.encode(
            claims,
            self.apple_private_key,
            algorithm="ES256",
            headers={"kid": self.apple_key_id},
        )

    def _cron_rotate_apple_client_secret(self):
        """Scheduled monthly (see data/ir_cron_apple_client_secret.xml) -
        comfortably inside Apple's 180-day cap on the minted JWT above.
        """
        providers = self.search(
            [
                ("apple_team_id", "!=", False),
                ("apple_key_id", "!=", False),
                ("apple_private_key", "!=", False),
            ]
        )
        for provider in providers:
            provider.client_secret = provider._mint_apple_client_secret()
            _logger.info(
                "Rotated the Apple client secret for auth.oauth.provider "
                "%s (%s).",
                provider.name,
                provider.id,
            )
