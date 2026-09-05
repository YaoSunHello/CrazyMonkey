from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.runtime.model import (
    MAX_OUTPUT_TOKENS,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    TIMEOUT_SECONDS,
    RuntimeModel,
    RuntimeModelError,
    _RejectRedirects,
    from_environment,
)


class Response(io.BytesIO):
    status = 200


def response_for(content="{}", *, provider="openai", stop=None):
    if provider == "openai":
        envelope = {"choices": [{"finish_reason": stop or "stop", "message": {"content": content}}]}
    else:
        envelope = {"stop_reason": stop or "end_turn", "content": [{"type": "text", "text": content}]}
    return Response(json.dumps(envelope).encode())


class RuntimeModelTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_no_credentials_returns_none(self):
        self.assertIsNone(from_environment())

    def test_credential_precedence_and_model_override(self):
        os.environ.update(OPENAI_API_KEY="test-openai-key", ANTHROPIC_API_KEY="test-anthropic-key")
        self.assertEqual(from_environment().name, "openai/gpt-4.1-mini")
        os.environ["OPENAI_MODEL"] = "test-model"
        self.assertEqual(from_environment().name, "openai/test-model")
        del os.environ["OPENAI_API_KEY"]
        self.assertEqual(from_environment().name, "anthropic/claude-haiku-4-5-20251001")
        os.environ["ANTHROPIC_MODEL"] = "test-claude"
        self.assertEqual(from_environment().name, "anthropic/test-claude")

    def test_custom_endpoint_rejected_without_echoing_it(self):
        os.environ.update(OPENAI_API_KEY="secret-key", OPENAI_BASE_URL="https://wrong.example/secret")
        with self.assertRaises(RuntimeModelError) as caught:
            from_environment()
        self.assertNotIn("wrong.example", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_credentials_are_not_in_repr_or_configuration_errors(self):
        self.assertNotIn("secret-key", repr(RuntimeModel("openai", "test", "secret-key")))
        for provider, model, key in (("other", "test", "key"), ("openai", "bad\nmodel", "key"), ("openai", "test", "secret\nkey")):
            with self.subTest(provider=provider, model=model):
                with self.assertRaises(RuntimeModelError) as caught:
                    RuntimeModel(provider, model, key)
                self.assertNotIn(key, str(caught.exception))

    def test_openai_payload_timeout_and_result(self):
        model = RuntimeModel("openai", "test-model", "test-key")
        with patch("app.runtime.model.urlopen", return_value=response_for('{"operation":"sum"}')) as opened:
            result = model.complete_json("Plan the analysis.", {"columns": ["Revenue"]})
        self.assertEqual(result, {"operation": "sum"})
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(opened.call_args.kwargs["timeout"], TIMEOUT_SECONDS)
        body = json.loads(request.data)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["max_completion_tokens"], MAX_OUTPUT_TOKENS)
        self.assertFalse(body["store"])
        self.assertEqual(json.loads(body["messages"][1]["content"]), {"columns": ["Revenue"]})

    def test_anthropic_payload_and_result(self):
        model = RuntimeModel("anthropic", "test-model", "test-key")
        with patch("app.runtime.model.urlopen", return_value=response_for('{"operation":"count"}', provider="anthropic")) as opened:
            self.assertEqual(model.complete_json("Plan.", {}), {"operation": "count"})
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.get_header("X-api-key"), "test-key")
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
        body = json.loads(request.data)
        self.assertEqual(body["max_tokens"], MAX_OUTPUT_TOKENS)
        self.assertTrue(body["system"].startswith("Plan."))

    def test_malformed_json_objects_fail_closed(self):
        invalid = ["not-json", "[]", "null", "123", '```json\n{}\n```', '{"x":NaN}', '{"x":1e1000}', '{"x":1,"x":2}']
        for content in invalid:
            with self.subTest(content=content):
                with patch("app.runtime.model.urlopen", return_value=response_for(content)):
                    with self.assertRaises(RuntimeModelError):
                        RuntimeModel("openai", "test", "key").complete_json("Plan.", {})

    def test_invalid_envelopes_and_truncation_fail_closed(self):
        responses = [Response(b"not-json"), Response(b"[]"), Response(b"{}"), response_for("{}", stop="length"), response_for("{}", provider="anthropic", stop="max_tokens")]
        for index, response in enumerate(responses):
            with self.subTest(index=index):
                provider = "anthropic" if index == len(responses) - 1 else "openai"
                with patch("app.runtime.model.urlopen", return_value=response):
                    with self.assertRaises(RuntimeModelError):
                        RuntimeModel(provider, "test", "key").complete_json("Plan.", {})

    def test_oversized_input_rejected_before_network(self):
        with patch("app.runtime.model.urlopen") as opened:
            with self.assertRaisesRegex(RuntimeModelError, "request exceeds"):
                RuntimeModel("openai", "test", "key").complete_json("Plan.", {"source": "x" * MAX_REQUEST_BYTES})
        opened.assert_not_called()

    def test_nonfinite_or_unserializable_input_rejected_before_network(self):
        for payload in ({"x": float("nan")}, {"x": object()}):
            with patch("app.runtime.model.urlopen") as opened:
                with self.assertRaises(RuntimeModelError):
                    RuntimeModel("openai", "test", "key").complete_json("Plan.", payload)
                opened.assert_not_called()

    def test_oversized_response_rejected(self):
        with patch("app.runtime.model.urlopen", return_value=Response(b"x" * (MAX_RESPONSE_BYTES + 1))):
            with self.assertRaisesRegex(RuntimeModelError, "response exceeds"):
                RuntimeModel("openai", "test", "key").complete_json("Plan.", {})

    def test_slow_response_deadline(self):
        with patch("app.runtime.model.urlopen", return_value=response_for()), patch("app.runtime.model.time.monotonic", side_effect=[0, TIMEOUT_SECONDS + 1]):
            with self.assertRaisesRegex(RuntimeModelError, "deadline"):
                RuntimeModel("openai", "test", "key").complete_json("Plan.", {})

    def test_connection_and_provider_errors_do_not_expose_details(self):
        for error in (URLError("secret-key private financial text"), HTTPError("https://api.example/secret-key", 401, "private financial text", {}, io.BytesIO(b"sensitive source"))):
            with patch("app.runtime.model.urlopen", side_effect=error):
                with self.assertRaises(RuntimeModelError) as caught:
                    RuntimeModel("openai", "test", "secret-key").complete_json("private financial text", {})
                rendered = str(caught.exception)
                self.assertNotIn("secret-key", rendered)
                self.assertNotIn("private financial text", rendered)
                self.assertNotIn("sensitive source", rendered)
                self.assertTrue(caught.exception.__suppress_context__)

    def test_redirects_are_blocked(self):
        with self.assertRaisesRegex(RuntimeModelError, "redirect"):
            _RejectRedirects().redirect_request(None, None, 302, "moved", {}, "https://other.example")


if __name__ == "__main__":
    unittest.main()
