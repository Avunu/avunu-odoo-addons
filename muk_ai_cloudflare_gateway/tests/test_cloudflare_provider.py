# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import json
from unittest.mock import Mock, patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCloudflareProvider(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["muk_ai.provider"].create(
            {
                "name": "cloudflare",
                "cloudflare_account_id": "acct123",
                "cloudflare_api_token": "workers-ai-token",
            }
        )

    def test_headers_use_cloudflare_api_token_not_api_key(self):
        self.provider.api_key = "should-be-ignored"
        headers = self.provider._get_client().headers()
        self.assertEqual(headers["Authorization"], "Bearer workers-ai-token")

    def test_headers_include_gateway_id_when_set(self):
        self.provider.cloudflare_gateway_id = "my-gateway"
        headers = self.provider._get_client().headers()
        self.assertEqual(headers["cf-aig-gateway-id"], "my-gateway")

    def test_headers_omit_gateway_id_when_not_set(self):
        headers = self.provider._get_client().headers()
        self.assertNotIn("cf-aig-gateway-id", headers)

    def test_authenticated_follows_cloudflare_api_token(self):
        self.assertTrue(self.provider._get_client().authenticated)
        self.provider.cloudflare_api_token = False
        self.assertFalse(self.provider._get_client().authenticated)

    def test_custom_url_is_the_only_region(self):
        self.assertEqual(self.provider._valid_regions(), ["custom"])

    def test_api_url_field_is_derived_on_create(self):
        # Regression: creating with an account id and no api_url used to
        # trip core's "custom URL is required" constraint, since api_url
        # was a plain field nothing ever filled in.
        self.assertEqual(
            self.provider.api_url,
            "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1",
        )

    def test_api_url_field_updates_when_account_id_changes(self):
        self.provider.cloudflare_account_id = "other-account"
        self.assertEqual(
            self.provider.api_url,
            "https://api.cloudflare.com/client/v4/accounts/other-account/ai/v1",
        )

    def test_api_url_is_derived_from_account_id(self):
        self.assertEqual(
            self.provider._get_client().api_url,
            "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1",
        )

    def test_api_url_empty_without_account_id(self):
        self.provider.cloudflare_account_id = False
        self.assertEqual(self.provider._get_client().api_url, "")

    def test_other_providers_api_url_is_unaffected(self):
        openai_provider = self.env["muk_ai.provider"].create(
            {
                "name": "openai",
                "api_key": "sk-test",
                "api_region": "custom",
                "api_url": "https://my-resource.openai.azure.com/openai/v1",
            }
        )
        self.assertEqual(
            openai_provider.api_url,
            "https://my-resource.openai.azure.com/openai/v1",
        )

    def test_list_models_requires_account_id(self):
        self.provider.cloudflare_account_id = False
        with self.assertRaises(UserError):
            self.provider._get_client().list_models()

    def _mock_search_response(self, results):
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {"result": results}
        return response

    def test_list_models_keeps_only_known_tasks(self):
        results = [
            {
                "name": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "task": {"name": "Text Generation"},
                "properties": [
                    {"property_id": "context_window", "value": "128000"}
                ],
            },
            {
                "name": "@cf/black-forest-labs/flux-1-schnell",
                "task": {"name": "Text-to-Image"},
            },
            {
                "name": "@cf/baai/bge-base-en-v1.5",
                "task": {"name": "Text Embeddings"},
            },
        ]
        with patch.object(
            type(self.provider._get_client()),
            "_http_session",
            return_value=Mock(get=Mock(return_value=self._mock_search_response(results))),
        ):
            models = self.provider._get_client().list_models()

        technical_names = {m["technical_name"] for m in models}
        self.assertEqual(
            technical_names,
            {
                "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "@cf/black-forest-labs/flux-1-schnell",
            },
        )
        chat_model = next(
            m
            for m in models
            if m["technical_name"] == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        )
        self.assertEqual(chat_model["modality"], "chat")
        self.assertEqual(chat_model["context_window"], 128000)
        self.assertEqual(chat_model["input_rate"], 0.0)

    def _mock_session(self, responder):
        """A _http_session() replacement whose .get(url, params=...) result
        is decided by `responder(url, params)`.
        """
        def get(url, headers=None, params=None, timeout=None):
            return self._mock_search_response(responder(url, params))

        return Mock(get=Mock(side_effect=get))

    def test_list_models_uses_gateway_filter_when_set(self):
        # Spend-limit filter values come back bare; model search results
        # are always "@cf/"-prefixed - this is the real shape of both.
        self.provider.cloudflare_gateway_id = "millrun"
        allowed = "ibm-granite/granite-4.0-h-micro"
        prefixed = f"@cf/{allowed}"
        searched_names = []

        def responder(url, params):
            if "ai-gateway/gateways/millrun" in url:
                return {
                    "spend_limits": {
                        "rules": [
                            {
                                "model": {"mode": "filter", "values": [allowed]},
                            }
                        ]
                    }
                }
            searched_names.append(params.get("search"))
            return [{"name": prefixed, "task": {"name": "Text Generation"}}]

        with patch.object(
            type(self.provider._get_client()),
            "_http_session",
            return_value=self._mock_session(responder),
        ):
            models = self.provider._get_client().list_models()

        self.assertEqual(searched_names, [allowed])
        self.assertEqual({m["technical_name"] for m in models}, {prefixed})

    def test_gateway_filter_search_discards_unrelated_matches(self):
        # Cloudflare's "search" param matches by name or description, so a
        # loosely-related result the gateway does NOT allow can come back
        # alongside the one that was actually asked for - only the exact
        # (prefix-normalized) match should survive.
        self.provider.cloudflare_gateway_id = "millrun"
        allowed = "ibm-granite/granite-4.0-h-micro"

        def responder(url, params):
            if "ai-gateway/gateways/millrun" in url:
                return {
                    "spend_limits": {
                        "rules": [
                            {"model": {"mode": "filter", "values": [allowed]}}
                        ]
                    }
                }
            return [
                {"name": f"@cf/{allowed}", "task": {"name": "Text Generation"}},
                {
                    "name": "@cf/ibm-granite/granite-4.0-h-micro-preview",
                    "task": {"name": "Text Generation"},
                },
            ]

        with patch.object(
            type(self.provider._get_client()),
            "_http_session",
            return_value=self._mock_session(responder),
        ):
            models = self.provider._get_client().list_models()

        self.assertEqual({m["technical_name"] for m in models}, {f"@cf/{allowed}"})

    def test_list_models_falls_back_to_full_catalog_without_filter(self):
        self.provider.cloudflare_gateway_id = "millrun"

        def responder(url, params):
            if "ai-gateway/gateways/millrun" in url:
                return {"spend_limits": {"rules": []}}
            return [
                {
                    "name": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                    "task": {"name": "Text Generation"},
                }
            ]

        with patch.object(
            type(self.provider._get_client()),
            "_http_session",
            return_value=self._mock_session(responder),
        ):
            models = self.provider._get_client().list_models()

        self.assertEqual(
            {m["technical_name"] for m in models},
            {"@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        )

    def test_action_fetch_cloudflare_models_creates_and_updates(self):
        model_vals = {
            "technical_name": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "name": "llama-3.3-70b-instruct-fp8-fast",
            "modality": "chat",
            "context_window": 128000,
            "input_rate": 0.0,
            "output_rate": 0.0,
            "notes": "test",
        }
        with patch.object(
            type(self.provider._get_client()), "list_models", return_value=[model_vals]
        ):
            self.provider.action_fetch_cloudflare_models()
            created = self.env["muk_ai.model"].search(
                [
                    ("provider_id", "=", self.provider.id),
                    ("technical_name", "=", model_vals["technical_name"]),
                ]
            )
            self.assertEqual(len(created), 1)

            updated_vals = dict(model_vals, context_window=200000)
            with patch.object(
                type(self.provider._get_client()),
                "list_models",
                return_value=[updated_vals],
            ):
                self.provider.action_fetch_cloudflare_models()

            self.assertEqual(len(created), 1)
            self.assertEqual(created.context_window, 200000)


@tagged("post_install", "-at_install")
class TestCloudflareChatCompletions(TransactionCase):
    """The Chat Completions translation - request()'s core job, and the
    part that broke silently until it was exercised for real: MuK AI's
    OpenAIProvider (which this provider used to subclass) targets
    OpenAI's Responses API, which Cloudflare doesn't implement.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["muk_ai.provider"].create(
            {
                "name": "cloudflare",
                "cloudflare_account_id": "acct123",
                "cloudflare_api_token": "workers-ai-token",
            }
        )
        cls.client = cls.provider._get_client()

    # ----------------------------------------------------------
    # Canonical inputs -> messages
    # ----------------------------------------------------------

    def test_plain_user_message(self):
        # Content is always the content-blocks array, never collapsed to a
        # bare string - Cloudflare's schema rejects a string here even for
        # a text-only message.
        messages = self.client._inputs_to_messages(
            [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}]
        )
        self.assertEqual(
            messages, [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        )

    def test_image_attachment_becomes_image_url_block(self):
        messages = self.client._inputs_to_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "muk_ai_attachment",
                            "strategy": "image",
                            "mimetype": "image/png",
                            "data_b64": "AAAA",
                        }
                    ],
                }
            ]
        )
        self.assertEqual(
            messages,
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAAA"},
                        }
                    ],
                }
            ],
        )

    def test_function_call_items_merge_into_one_assistant_message(self):
        messages = self.client._inputs_to_messages(
            [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "search",
                    "arguments": '{"q": "a"}',
                },
                {
                    "type": "function_call",
                    "call_id": "c2",
                    "name": "search",
                    "arguments": '{"q": "b"}',
                },
            ]
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "assistant")
        # Empty string, not None: Cloudflare's schema rejects content:
        # null even on a tool_calls-only assistant message.
        self.assertEqual(messages[0]["content"], "")
        self.assertEqual(len(messages[0]["tool_calls"]), 2)
        self.assertEqual(messages[0]["tool_calls"][0]["id"], "c1")
        self.assertEqual(
            messages[0]["tool_calls"][1]["function"]["arguments"], '{"q": "b"}'
        )

    def test_function_call_output_becomes_tool_message(self):
        messages = self.client._inputs_to_messages(
            [{"type": "function_call_output", "call_id": "c1", "output": {"ok": True}}]
        )
        self.assertEqual(
            messages,
            [{"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'}],
        )

    def test_tools_to_openai_wraps_and_dedupes(self):
        tools = self.client._tools_to_openai(
            [
                {"name": "search", "description": "Search", "parameters": {}},
                {"name": "search", "description": "duplicate", "parameters": {}},
            ]
        )
        self.assertEqual(len(tools), 1)
        self.assertEqual(
            tools[0],
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {},
                },
            },
        )

    # ----------------------------------------------------------
    # Response parsing
    # ----------------------------------------------------------

    def test_parse_response_text_only(self):
        result = self.client._parse_response(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            }
        )
        self.assertEqual(result["text"], "Hello!")
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(
            result["carry_inputs"],
            [{"role": "assistant", "content": [{"type": "output_text", "text": "Hello!"}]}],
        )
        self.assertEqual(result["usage"]["input_tokens"], 10)
        self.assertEqual(result["usage"]["output_tokens"], 3)

    def test_parse_response_with_tool_call(self):
        result = self.client._parse_response(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"q": "cloudflare"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            }
        )
        self.assertEqual(result["text"], "")
        self.assertEqual(
            result["tool_calls"],
            [
                {
                    "call_id": "call_1",
                    "name": "search",
                    "arguments": {"q": "cloudflare"},
                    "_parse_error": None,
                }
            ],
        )
        self.assertEqual(
            result["carry_inputs"],
            [
                {
                    "type": "function_call",
                    "name": "search",
                    "arguments": '{"q": "cloudflare"}',
                    "call_id": "call_1",
                }
            ],
        )

    # ----------------------------------------------------------
    # request() end-to-end (non-streaming)
    # ----------------------------------------------------------

    def test_request_posts_chat_completions_shape(self):
        captured = {}

        def fake_post_json(path, body, timeout=None):
            captured["path"] = path
            captured["body"] = body
            return {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        with patch.object(type(self.client), "_post_json", fake_post_json):
            result = self.client.request(
                inputs=[
                    {"role": "user", "content": [{"type": "input_text", "text": "hi"}]}
                ],
                tools_schema=[{"name": "search", "parameters": {}}],
            )

        self.assertEqual(captured["path"], "/chat/completions")
        self.assertEqual(
            captured["body"]["messages"],
            [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        )
        self.assertEqual(captured["body"]["tools"][0]["function"]["name"], "search")
        self.assertNotIn("input", captured["body"])
        self.assertEqual(result["text"], "ok")

    # ----------------------------------------------------------
    # Double-encoded tool arguments (observed from granite-4.0-h-micro)
    # ----------------------------------------------------------

    def test_parse_tool_arguments_unwraps_double_encoding(self):
        # The assembled `arguments` string is itself a JSON string
        # containing the escaped object, not the object directly.
        double_encoded = json.dumps(json.dumps({"model": "res.partner"}))
        args, error = self.client._parse_tool_arguments(double_encoded)
        self.assertEqual(args, {"model": "res.partner"})
        self.assertIsNone(error)

    def test_parse_tool_arguments_normal_encoding_still_works(self):
        args, error = self.client._parse_tool_arguments('{"model": "res.partner"}')
        self.assertEqual(args, {"model": "res.partner"})
        self.assertIsNone(error)

    def test_parse_tool_arguments_reports_error_when_never_an_object(self):
        args, error = self.client._parse_tool_arguments('"just a string"')
        self.assertEqual(args, {})
        self.assertIsNotNone(error)

    def test_double_encoded_arguments_survive_full_streaming_round_trip(self):
        double_encoded = json.dumps(json.dumps({"model": "res.partner"}))
        chunks = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {
                                        "name": "describe_model",
                                        "arguments": "",
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": double_encoded}}
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]
        with patch.object(type(self.client), "_post_stream", return_value=iter(chunks)):
            result = self.client._stream({"model": "x", "messages": []}, lambda *a: None)

        self.assertEqual(
            result["tool_calls"][0]["arguments"], {"model": "res.partner"}
        )

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def test_stream_assembles_text_and_tool_calls_from_deltas(self):
        chunks = [
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {"name": "search", "arguments": ""},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": '{"q":1}'}}
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        ]
        events = []

        def on_delta(kind, payload):
            events.append((kind, payload))

        with patch.object(type(self.client), "_post_stream", return_value=iter(chunks)):
            result = self.client._stream({"model": "x", "messages": []}, on_delta)

        self.assertEqual(result["text"], "Hello")
        self.assertEqual(result["tool_calls"][0]["name"], "search")
        self.assertEqual(result["tool_calls"][0]["arguments"], {"q": 1})
        self.assertEqual(result["usage"]["input_tokens"], 5)
        self.assertIn(("text", {"delta": "Hel"}), events)
        self.assertIn(("tool_start", {"call_id": "call_1", "name": "search"}), events)
        self.assertIn(("tool_args", {"call_id": "call_1", "delta": '{"q":1}'}), events)
