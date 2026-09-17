# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from __future__ import annotations

import json

import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_ai.providers.region import CUSTOM

CLOUDFLARE_API_BASE = 'https://api.cloudflare.com/client/v4'
MODELS_SEARCH_PAGE_SIZE = 100

# Cloudflare's model search API groups models by task; only these map onto
# a modality muk_ai.model actually supports (chat, image). Everything else
# (embeddings, ASR, TTS, translation, guardrails, ...) is skipped.
TASK_MODALITY = {
    'Text Generation': 'chat',
    'Text-to-Image': 'image',
}

# property_id values seen on Cloudflare model objects that hold the
# context window, checked case-insensitively since this isn't documented.
CONTEXT_WINDOW_PROPERTY_IDS = ('context_window', 'max_input_tokens', 'context_length')


class CloudflareProvider(ProviderBase):
    """Cloudflare Workers AI, via its OpenAI-*Chat-Completions*-compatible
    endpoint (``/v1/chat/completions``) - not the newer Responses API
    (``/v1/responses``) MuK AI's own `OpenAIProvider` targets, which
    Cloudflare doesn't implement. Requests/responses here are hand-built
    against the Chat Completions wire format rather than inherited from
    that adapter, so this subclasses `ProviderBase` directly - the same
    shape as `AnthropicProvider`, which solves the same "not the Responses
    API" translation problem and is this class's structural template.

    Everything account-specific is derived from a single **Account ID**
    field instead of asking for it as a raw URL:

    - The chat endpoint (`api_url`, inherited from `ProviderBase`) is
      built as ``https://api.cloudflare.com/client/v4/accounts/<id>/ai/
      v1`` by a compute override on `muk_ai.provider.api_url` itself
      (models/provider.py), since region is always 'custom' here.
    - `list_models()` calls Cloudflare's *account* API (a different base
      path, `/client/v4` directly rather than `.../ai/v1`) to populate the
      model catalogue - narrowed to whatever a configured Gateway ID
      actually allows, when it restricts anything (see its docstring).

    Two further adjustments:

    - The credential lives in this provider's own **API Token** field
      (`cloudflare_api_token`), not the generic **API Key** field other
      providers use - overriding `_api_key` is enough for that, since
      `authenticated`/`api_key` on the base class both derive from it.
    - Routing the request through a Cloudflare AI Gateway (for usage
      tracking/billing) is a header, not a URL change
      (https://developers.cloudflare.com/ai-gateway/usage/providers/
      workersai/): setting **Gateway ID** sends `cf-aig-gateway-id` on
      every inference request (not on the account-API calls `list_models`
      makes - that header has no meaning there).
    """

    name = 'cloudflare'
    label = 'Cloudflare Workers AI'
    default_model = '@cf/meta/llama-3.3-70b-instruct-fp8-fast'
    default_url = ''
    regions = (CUSTOM,)

    @property
    def _api_key(self) -> str:
        return self.provider.sudo().cloudflare_api_token or ''

    def headers(self) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        if gateway_id := self.provider.sudo().cloudflare_gateway_id:
            headers['cf-aig-gateway-id'] = gateway_id
        return headers

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def request(
        self,
        inputs,
        tools_schema=None,
        text_schema=None,
        on_delta=None,
        model=None,
        enable_web_search=False,
        enable_code_interpreter=False,
        extra=None,
    ) -> dict:
        """Build and run a Chat Completions request.

        `text_schema` (structured JSON output), web search, and code
        interpreter are not implemented - Cloudflare's compat layer's
        support for the first isn't confirmed, and this provider never
        declares `supports_web_search`/`supports_code_interpreter`, so
        the base class never asks for the other two.
        """
        body = {
            'model': self.model_for(model),
            'messages': self._inputs_to_messages(self._wire_items(inputs)),
        }
        if self.max_tokens:
            body['max_tokens'] = self.max_tokens
        if tools := self._tools_to_openai(tools_schema):
            body['tools'] = tools
        if callable(on_delta):
            return self._stream(body, on_delta)
        return self._parse_response(self._post_json('/chat/completions', body))

    # ----------------------------------------------------------
    # Canonical inputs -> Chat Completions messages
    # ----------------------------------------------------------

    @classmethod
    def _inputs_to_messages(cls, inputs) -> list[dict]:
        """Convert canonical inputs into Chat Completions messages.

        Unlike Anthropic, Chat Completions tolerates consecutive
        same-role messages (no strict user/assistant alternation), so
        plain content items never need merging - only a turn's
        `function_call` items do, since Chat Completions bundles them
        onto one assistant message's `tool_calls` array rather than one
        message per call. They're always merged into the immediately
        preceding message: this provider is the only one that ever
        writes them here, and always writes any text for a turn
        immediately before that turn's tool calls (see `_parse_response`/
        `_stream`), so the ordering this relies on is self-controlled.
        """
        messages = []
        for item in inputs or []:
            item_type = item.get('type')
            role = item.get('role')

            if item_type == 'function_call':
                try:
                    arguments = json.loads(item.get('arguments') or '{}')
                except ValueError:
                    arguments = {}
                tool_call = {
                    'id': item.get('call_id'),
                    'type': 'function',
                    'function': {
                        'name': item.get('name'),
                        'arguments': json.dumps(arguments, default=str),
                    },
                }
                if messages and messages[-1].get('role') == 'assistant':
                    messages[-1].setdefault('tool_calls', []).append(tool_call)
                else:
                    # Cloudflare's schema rejects content: null here (it
                    # wants 'role'+'content' present and string-typed even
                    # on a tool_calls-only message) - empty string, not None.
                    messages.append(
                        {'role': 'assistant', 'content': '', 'tool_calls': [tool_call]}
                    )
                continue

            if item_type == 'function_call_output':
                output = item.get('output')
                if not isinstance(output, str):
                    output = json.dumps(output, default=str)
                messages.append(
                    {
                        'role': 'tool',
                        'tool_call_id': item.get('call_id'),
                        'content': output,
                    }
                )
                continue

            if role in ('system', 'user', 'assistant'):
                blocks = cls._content_to_openai(item.get('content'))
                if blocks:
                    # Always the content-blocks array, never collapsed to a
                    # plain string - Cloudflare's schema rejects a bare
                    # string here even for text-only messages.
                    messages.append({'role': role, 'content': blocks})

        return messages

    @classmethod
    def _content_to_openai(cls, content) -> list[dict]:
        """Convert canonical content (string or block list) into Chat
        Completions content blocks."""
        if isinstance(content, str):
            return [{'type': 'text', 'text': content}] if content else []
        blocks = []
        for chunk in content or []:
            if not isinstance(chunk, dict):
                continue
            if chunk.get('type') == 'muk_ai_attachment':
                blocks.append(cls._attachment_to_openai(chunk))
            elif chunk.get('text'):
                blocks.append({'type': 'text', 'text': chunk['text']})
        return blocks

    @staticmethod
    def _attachment_to_openai(block: dict) -> dict:
        """Convert an attachment block into a Chat Completions content block.

        Chat Completions has no generic file-attachment block like the
        Responses API's `input_file` - anything that isn't an image falls
        back to inline text, same as when no strategy matches at all.
        """
        strategy = block.get('strategy')
        mimetype = block.get('mimetype') or 'application/octet-stream'
        if strategy == 'image':
            return {
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{mimetype};base64,{block.get("data_b64", "")}'
                },
            }
        filename = block.get('filename') or 'attachment'
        text = block.get('inline_text') or ''
        prefix = f'--- File: {filename} ({mimetype}) ---\n'
        if block.get('truncated'):
            text += '\n[truncated]'
        return {'type': 'text', 'text': prefix + text}

    @staticmethod
    def _tools_to_openai(tools_schema) -> list[dict]:
        """Convert tool schemas to Chat Completions tool definitions,
        deduplicated by name.
        """
        if not tools_schema:
            return []
        seen = set()
        out = []
        for tool in tools_schema:
            name = tool['name']
            if name in seen:
                continue
            seen.add(name)
            out.append(
                {
                    'type': 'function',
                    'function': {
                        'name': name,
                        'description': tool.get('description') or '',
                        'parameters': tool.get('parameters')
                        or {'type': 'object', 'properties': {}},
                    },
                }
            )
        return out

    # ----------------------------------------------------------
    # Chat Completions response -> canonical result
    # ----------------------------------------------------------

    @staticmethod
    def _parse_tool_arguments(raw) -> tuple[dict, str | None]:
        """Parse tool-call arguments, unwrapping a level of double-encoding
        some Workers AI models produce.

        Normally `raw` is a JSON object string, e.g. '{"model": "x"}',
        and the base implementation's single `json.loads` is enough. At
        least one model observed in the wild (granite-4.0-h-micro) instead
        streams `arguments` as a JSON *string* containing the escaped
        object - '"{\\n \\"model\\": \\"x\\"}"' - so one decode yields a
        Python str, not a dict. Decoding once more recovers the real
        object; if it's still not a dict after that, this reports a parse
        error (letting the model recover) rather than handing a string
        downstream to code that calls .get() on it expecting an object.
        """
        args, error = ProviderBase._parse_tool_arguments(raw)
        if isinstance(args, str):
            args, error = ProviderBase._parse_tool_arguments(args)
        if not isinstance(args, dict):
            return {}, f'Tool arguments were not a JSON object: {raw!r}'
        return args, error

    @classmethod
    def _tool_calls_from_message(cls, tool_calls_raw: list) -> tuple[list, list]:
        """Return (tool_calls, function_call carry items) from a message's
        `tool_calls` array - shared by the streaming and non-streaming
        paths once each has assembled one.
        """
        tool_calls = []
        carries = []
        for entry in tool_calls_raw or []:
            call_id = entry.get('id')
            func = entry.get('function') or {}
            name = func.get('name')
            args, parse_error = cls._parse_tool_arguments(func.get('arguments'))
            tool_calls.append(
                {
                    'call_id': call_id,
                    'name': name,
                    'arguments': args,
                    '_parse_error': parse_error,
                }
            )
            carries.append(
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(args, default=str),
                    'call_id': call_id,
                }
            )
        return tool_calls, carries

    @classmethod
    def _build_result(cls, text: str, tool_calls_raw: list, usage_raw: dict) -> dict:
        text = text.strip()
        tool_calls, function_call_carries = cls._tool_calls_from_message(tool_calls_raw)
        carry_inputs = []
        if text:
            carry_inputs.append(
                {'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}
            )
        carry_inputs.extend(function_call_carries)
        return {
            'text': text,
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': cls._usage(
                input_tokens=usage_raw.get('prompt_tokens'),
                output_tokens=usage_raw.get('completion_tokens'),
            ),
        }

    def _parse_response(self, payload: dict) -> dict:
        choice = (payload.get('choices') or [{}])[0]
        message = choice.get('message') or {}
        content = message.get('content')
        text = content if isinstance(content, str) else ''
        result = self._build_result(
            text, message.get('tool_calls'), payload.get('usage') or {}
        )
        if choice.get('finish_reason') == 'length':
            self._apply_truncation(result, limit=self.max_tokens)
        return result

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, body: dict, on_delta) -> dict:
        body = {**body, 'stream': True}
        text_parts = []
        tool_calls_by_index: dict[int, dict] = {}
        usage_raw = {}
        finish_reason = None
        for chunk in self._post_stream('/chat/completions', body):
            for choice in chunk.get('choices') or []:
                delta = choice.get('delta') or {}
                if content := delta.get('content'):
                    text_parts.append(content)
                    self._call_on_delta(on_delta, 'text', {'delta': content})
                for tc_delta in delta.get('tool_calls') or []:
                    self._apply_tool_call_delta(tc_delta, tool_calls_by_index, on_delta)
                if choice.get('finish_reason'):
                    finish_reason = choice['finish_reason']
            if chunk.get('usage'):
                usage_raw = chunk['usage']

        tool_calls_raw = [
            {
                'id': entry['call_id'],
                'function': {'name': entry['name'], 'arguments': entry['arguments']},
            }
            for _, entry in sorted(tool_calls_by_index.items())
        ]
        result = self._build_result(''.join(text_parts), tool_calls_raw, usage_raw)
        if finish_reason == 'length':
            self._apply_truncation(result, on_delta, self.max_tokens)
        return result

    @staticmethod
    def _apply_tool_call_delta(tc_delta: dict, tool_calls_by_index: dict, on_delta) -> None:
        index = tc_delta.get('index', 0)
        entry = tool_calls_by_index.get(index)
        if entry is None:
            entry = {
                'call_id': tc_delta.get('id'),
                'name': (tc_delta.get('function') or {}).get('name'),
                'arguments': '',
            }
            tool_calls_by_index[index] = entry
            CloudflareProvider._call_on_delta(
                on_delta, 'tool_start', {'call_id': entry['call_id'], 'name': entry['name']}
            )
        if args_delta := (tc_delta.get('function') or {}).get('arguments'):
            entry['arguments'] += args_delta
            CloudflareProvider._call_on_delta(
                on_delta, 'tool_args', {'call_id': entry['call_id'], 'delta': args_delta}
            )

    # ----------------------------------------------------------
    # Account API (not the AI Gateway-routed inference endpoint)
    # ----------------------------------------------------------

    def _cloudflare_account_get(self, path: str, params: dict | None = None) -> dict:
        """GET a Cloudflare account API path and return the decoded body.

        Not self.headers(): that's built for the AI-Gateway-routed
        inference endpoint (adds cf-aig-gateway-id), which has no meaning
        on this general account API.
        """
        try:
            response = self._http_session().get(
                f'{CLOUDFLARE_API_BASE}{path}',
                headers={'Authorization': f'Bearer {self.api_key}'},
                params=params,
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)
        return response.json()

    # ----------------------------------------------------------
    # Model catalogue
    # ----------------------------------------------------------

    def list_models(self) -> list[dict]:
        """Fetch this account's Workers AI models and return muk_ai.model
        create/write vals for the ones muk_ai can actually use.

        When Gateway ID is set and that gateway has a spend-limit rule
        filtering Workers AI to specific models
        (https://developers.cloudflare.com/ai-gateway/features/
        spend-limits/), only those models are fetched - matching what the
        gateway will actually serve rather than the account's full public
        catalog. A gateway with no such filter, or no Gateway ID at all,
        falls back to every model in the account's catalog.

        Cloudflare's model search API
        (https://developers.cloudflare.com/api/resources/ai/subresources/
        models/methods/list/) does not return pricing, so every model
        comes back with its rates at 0 - review and correct them before
        relying on cost tracking for any model imported this way.
        """
        account_id = self.provider.sudo().cloudflare_account_id
        if not account_id:
            raise UserError(_('Set an Account ID before fetching models.'))

        gateway_id = self.provider.sudo().cloudflare_gateway_id
        allowed_names = (
            self._gateway_model_filter(account_id, gateway_id) if gateway_id else None
        )
        if allowed_names:
            results = self._search_models_by_name(account_id, allowed_names)
        else:
            results = self._search_all_models(account_id)
        return self._normalize_models(results)

    def _gateway_model_filter(self, account_id: str, gateway_id: str) -> set[str]:
        """Return the model names a gateway's spend-limit rules restrict
        Workers AI to, or an empty set when nothing restricts it.
        """
        payload = self._cloudflare_account_get(
            f'/accounts/{account_id}/ai-gateway/gateways/{gateway_id}'
        )
        rules = ((payload.get('result') or {}).get('spend_limits') or {}).get(
            'rules'
        ) or []
        names = set()
        for rule in rules:
            model = rule.get('model') or {}
            if model.get('mode') == 'filter':
                names.update(model.get('values') or [])
        return names

    def _search_models_by_name(self, account_id: str, names: set[str]) -> list[dict]:
        path = f'/accounts/{account_id}/ai/models/search'
        results = []
        for name in sorted(names):
            payload = self._cloudflare_account_get(path, params={'search': name})
            results.extend(
                item
                for item in payload.get('result') or []
                if self._strip_cf_prefix(item.get('name') or item.get('id') or '')
                == self._strip_cf_prefix(name)
            )
        return results

    @staticmethod
    def _strip_cf_prefix(name: str) -> str:
        # Spend-limit filter values are bare ("ibm-granite/granite-4.0-h-
        # micro"); model search results are always "@cf/"-prefixed - compare
        # both stripped of it rather than assuming either side's shape.
        return name.removeprefix('@cf/')

    def _search_all_models(self, account_id: str) -> list[dict]:
        path = f'/accounts/{account_id}/ai/models/search'
        results = []
        page = 1
        while True:
            payload = self._cloudflare_account_get(
                path, params={'page': page, 'per_page': MODELS_SEARCH_PAGE_SIZE}
            )
            page_results = payload.get('result') or []
            results.extend(page_results)
            if len(page_results) < MODELS_SEARCH_PAGE_SIZE:
                return results
            page += 1

    def _normalize_models(self, results: list[dict]) -> list[dict]:
        """Cloudflare model search results -> muk_ai.model vals, deduplicated
        by technical name and limited to modalities muk_ai supports.
        """
        models = {}
        for item in results:
            task = (item.get('task') or {}).get('name')
            modality = TASK_MODALITY.get(task)
            technical_name = item.get('name') or item.get('id')
            if not modality or not technical_name or technical_name in models:
                continue
            models[technical_name] = {
                'technical_name': technical_name,
                'name': technical_name.rsplit('/', 1)[-1],
                'modality': modality,
                'context_window': self._extract_context_window(item),
                'input_rate': 0.0,
                'output_rate': 0.0,
                'notes': _(
                    "Imported from Cloudflare's model catalog. Pricing "
                    "is not returned by that API - check "
                    "https://developers.cloudflare.com/workers-ai/"
                    "platform/pricing/ and correct the rates below "
                    "before relying on cost tracking."
                ),
            }
        return list(models.values())

    @staticmethod
    def _extract_context_window(item: dict) -> int:
        for prop in item.get('properties') or []:
            property_id = str(prop.get('property_id') or '').lower()
            if property_id in CONTEXT_WINDOW_PROPERTY_IDS:
                try:
                    return int(prop.get('value') or 0)
                except (TypeError, ValueError):
                    return 0
        return 0
