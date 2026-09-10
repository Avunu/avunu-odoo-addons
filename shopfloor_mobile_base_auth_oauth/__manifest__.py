# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Shopfloor Mobile Base auth via Google/Apple sign-in",
    "summary": "Provides authentication via Google/Apple social login to "
    "Shopfloor base mobile apps",
    "version": "18.0.1.0.2",
    "category": "Inventory",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "shopfloor_mobile_base",
        # Reused directly: the frontend imports this module's login.esm.js
        # verbatim to get the API-KEY request transport (see
        # static/src/login.esm.js), and the backend reuses its
        # `_allowed_api_key_ids()` app-level allow-list check.
        "shopfloor_mobile_base_auth_api_key",
        # OCA's OIDC extension of core auth_oauth: JWKS-verified id_token,
        # PKCE, and the id_token_code flow this module builds on.
        "auth_oidc",
        # Apple's private key is a real secret at rest - store it out of
        # the database where the deployment provides a server_environment
        # config file (see models/auth_oauth_provider.py).
        "server_environment",
    ],
    "data": [
        "views/shopfloor_app.xml",
        "views/auth_oauth_provider.xml",
        "templates/assets.xml",
        "data/auth_oauth_provider_google.xml",
        "data/auth_oauth_provider_apple.xml",
        "data/ir_cron_apple_client_secret.xml",
    ],
}
