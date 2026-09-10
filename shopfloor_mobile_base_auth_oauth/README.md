# Shopfloor Mobile Base auth via Google/Apple sign-in

Lets a technician sign into a Shopfloor mobile app (e.g. `shopfloor_repair_mobile`)
with their own Google or Apple account instead of typing an `auth.api.key` by
hand. Google/Apple's job is entirely a **login-time** alternative — once signed
in, the app holds a real `auth.api.key` and every REST call after that carries
it in the `API-KEY` header exactly as it would for an api_key-flavored app.
See `shopfloor_mobile_base_auth_api_key`, which this module reuses directly
rather than duplicating.

## Setup

1. Install this module. It adds `"oauth"` as a `shopfloor.app` auth type
   alongside the existing `"api_key"`.
2. **Google Cloud Console**: create an OAuth 2.0 Web client. Redirect URI must
   be `https://<host>/auth_oauth/signin` **exactly** — this is hardcoded in
   `auth_oidc`'s token-exchange call, not configurable per app. Set
   `client_id`/`client_secret` on the seeded *Google (Shopfloor)* provider and
   enable it.
3. **Apple Developer portal**: register an App ID and a Services ID (the
   Services ID is the `client_id`), enable Sign in with Apple, use the same
   redirect URL, generate a `.p8` signing key, and note the Team ID and Key
   ID. Fill in the seeded *Apple (Shopfloor)* provider's `apple_team_id` /
   `apple_key_id` / `apple_private_key`, then run
   `_cron_rotate_apple_client_secret()` once by hand (Settings > Technical >
   Scheduled Actions) to populate `client_secret` before enabling it — Apple
   doesn't issue a static one; it's minted here as a signed JWT, capped at
   Apple's own 180-day limit, and re-minted monthly by that same cron.
4. On the `shopfloor.app` record: set **Auth Type** to *Social login
   (Google/Apple)*, then **Allowed API key groups** (from the api_key module)
   to whichever group(s) technicians' keys already live in.
   - Leave **Auto-provision API key** off (the default) to keep today's
     policy: an admin creates each technician's `auth.api.key` by hand, and a
     signed-in technician with none is denied and told to ask for one.
   - Turn it on, and set **Group for auto-provisioned keys** (which must also
     be one of the app's own allowed groups), to mint a key automatically on
     first login instead.
5. Leave **Allow sign-up** off (the default) unless you actually want Odoo's
   own auth_oauth sign-up flow to run for an unmatched identity — see
   Limitations below for what "unmatched" means in practice before turning
   this on.

## Security notes, flagged explicitly rather than shipped silently

- **`/auth_oauth/signin` gets `csrf=False`.** Needed only for Apple, whose
  mandatory `response_mode=form_post` delivers its callback as a cross-site
  POST with no Odoo `csrf_token` attached. This endpoint's real security
  boundary is JWKS signature verification of the `id_token` plus PKCE — both
  untouched — not Odoo's ambient-session CSRF token, which was never a
  meaningful defense for a third-party redirect callback to begin with.
- **The login is instance-wide, not per-app.** Odoo's OAuth redirect URI is
  fixed at `/auth_oauth/signin`, so any *enabled* `auth.oauth.provider` shows
  up as a login button on **every** oauth-flavored Shopfloor app, and the same
  Google/Apple buttons also appear on the normal `/web/login` screen — there
  is no per-app provider allow-list. If a provider is only meant for one
  audience, its `enabled` flag is the only lever; don't enable a Shopfloor
  provider you don't want desktop staff logging in with too, or vice versa.
- **The API key travels as a URL fragment** (`#apikey=...`), never a query
  param, specifically so it never lands in server access logs or a `Referer`
  header. It's captured and stripped from the address bar before the app's
  router or any other code looks at it.

## Limitations

- **"Pre-existing accounts only" needs the account linked once, not just
  created.** Core `auth_oauth` matches an incoming Google/Apple identity to a
  `res.users` record by a stored `(oauth_uid, oauth_provider_id)` pair, never
  by matching login/email against an admin-created account — so a technician
  whose Odoo user was created the normal way (no prior OAuth login) is
  rejected on their *first* Google/Apple sign-in attempt regardless of the
  **Allow sign-up** setting above, not auto-linked to their existing account.
  Turning **Allow sign-up** on doesn't fix this either: it makes Odoo's
  sign-up flow create a brand-new, separate `res.users` record instead
  (duplicating, not linking, the existing technician account). Give each
  technician one normal `/web/login` Google/Apple sign-in first (which does
  link their account, since sign-up is allowed there by default) before they
  rely on it in the Shopfloor app, or link the pair by hand (`oauth_uid` +
  `oauth_provider_id` on their `res.users` record).
- **No automated test harness** covers OAuth click-through today (matching
  the rest of this stack) — verification is the manual pass in the original
  implementation plan.
