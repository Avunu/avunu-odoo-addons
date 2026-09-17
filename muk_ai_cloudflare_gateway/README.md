# MuK AI - Cloudflare AI Gateway Provider

Adds Cloudflare Workers AI as a selectable provider in **MuK AI > Configuration > Providers**, optionally routed through a Cloudflare AI Gateway so usage is tracked/billed under a named gateway.

## Why

Cloudflare Workers AI advertises "OpenAI compatibility," but that only covers the older **Chat Completions** API (`/v1/chat/completions`) - MuK AI's own `OpenAIProvider` targets OpenAI's newer **Responses** API (`/v1/responses`) exclusively, which Cloudflare doesn't implement at all. Subclassing that adapter therefore doesn't work: it fails validation on Cloudflare's side the moment a real conversation (not just a model listing) is attempted. This module implements its own provider against Chat Completions directly instead - the same "not the Responses API" translation problem MuK AI's own Anthropic provider already solves for a different vendor, and this module's structural template for it.

On top of that, Cloudflare's account id is all that's actually needed to use it: the endpoint URL and the account's available models can both be derived from it, rather than hand-typed.

## What it does

- Registers a new `cloudflare` provider, implementing Chat Completions' request/response/streaming shapes directly (tool-calling included) against a plain `ProviderBase` subclass, that takes an **Account ID** instead of a URL, and builds `https://api.cloudflare.com/client/v4/accounts/<id>/ai/v1` from it - the **Endpoint** field below still shows the result, it's just no longer something you type.
- Replaces the generic **API Key** field (hidden for this provider) with **API Token** - the Cloudflare API token itself, sent as `Authorization: Bearer <token>`.
- **Gateway ID**, if set, is sent as the `cf-aig-gateway-id` header, routing the request through that [AI Gateway](https://developers.cloudflare.com/ai-gateway/usage/providers/workersai/) for usage tracking - no URL change needed.
- A **Fetch Models** button (next to Test Connection) creates/updates a `muk_ai.model` record for each chat or image model available (everything else - embeddings, ASR, TTS, etc. - is skipped, since muk_ai only catalogs chat and image models). Running it again updates existing entries rather than duplicating them.
  - If **Gateway ID** is set *and* that gateway has a [spend-limit rule](https://developers.cloudflare.com/ai-gateway/features/spend-limits/) restricting Workers AI to specific models, only those models are fetched - matching what the gateway will actually serve.
  - Otherwise (no Gateway ID, or a gateway with no such restriction), every model in the account's public catalog is fetched.

## What it does not do

Cloudflare's model search API doesn't return pricing, so every fetched model comes in with its input/output rate at 0 and a note on the record saying so. **Review and correct pricing manually** (developers.cloudflare.com/workers-ai/platform/pricing/) before relying on MuK AI's per-session cost tracking for any Cloudflare model.

## Configuration

1. **MuK AI > Configuration > Providers**, create a provider with **Provider** = `Cloudflare Workers AI`.
2. **Account ID** = your Cloudflare account id (Account Home, right-hand sidebar).
3. **API Token** = a Cloudflare API token with Workers AI permissions.
4. **Gateway ID** = the gateway's ID from Account Home > AI Gateway, if you want usage tracked under it. Leave empty to call Workers AI directly.
5. **Test Connection**, then **Fetch Models** to populate the catalog - then open each imported model and fill in its real pricing.
