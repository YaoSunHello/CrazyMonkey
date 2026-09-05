from __future__ import annotations

import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.runtime.model import RuntimeModelError
from app.runtime.model_client import (
    GEMINI_BASE_URL,
    MAX_OUTPUT_TOKENS,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    TIMEOUT_SECONDS,
    GeminiClient,
    _BoundedStream,
    _bound_response,
    from_environment,
)


def sdk_response(content="{}", *, finish_reason="stop", response_id="chatcmpl-test"):
    return SimpleNamespace(
        id=response_id,
        choices=[SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(content=content, refusal=None, tool_calls=None, function_call=None),
        )],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )


class GeminiClientTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "LLM_API_KEY": "test-gemini-secret",
            "LLM_BASE_URL": GEMINI_BASE_URL,
            "LLM_MODEL": "gemini-exact-configured-model",
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.http_factory = patch("app.runtime.model_client.DefaultHttpxClient")
        self.http = self.http_factory.start()
        self.addCleanup(self.http_factory.stop)
        self.sdk_factory = patch("app.runtime.model_client.OpenAI")
        self.sdk = self.sdk_factory.start()
        self.addCleanup(self.sdk_factory.stop)
        self.sdk.return_value.chat.completions.create.return_value = sdk_response()

    def test_missing_configuration_fails_without_provider_fallback(self):
        for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
            with self.subTest(name=name), patch.dict(os.environ, {name: "", "OPENAI_API_KEY": "other-secret", "ANTHROPIC_API_KEY": "another-secret"}):
                with self.assertRaisesRegex(RuntimeModelError, name):
                    from_environment()
        self.sdk.assert_not_called()

    def test_no_model_default_and_no_whitespace_normalization(self):
        for model in ("", " gemini-test", "gemini-test\n", "x" * 129, "test-gemini-secret"):
            with self.subTest(model=model), patch.dict(os.environ, {"LLM_MODEL": model}):
                with self.assertRaises(RuntimeModelError):
                    from_environment()
        self.sdk.assert_not_called()

    def test_endpoint_allowlist_rejects_secret_urls_and_redirect_locations(self):
        urls = [
            "http://generativelanguage.googleapis.com/v1beta/openai",
            "https://generativelanguage.googleapis.com.evil.invalid/v1beta/openai",
            "https://private-user-secret@evil.invalid/v1beta/openai",
            GEMINI_BASE_URL + "?secret=test-gemini-secret",
            GEMINI_BASE_URL + "//",
            " " + GEMINI_BASE_URL,
            "https://api.openai.com/v1",
        ]
        for url in urls:
            with self.subTest(url=url), patch.dict(os.environ, {"LLM_BASE_URL": url}):
                with self.assertRaises(RuntimeModelError) as caught:
                    from_environment()
                self.assertNotIn(url, str(caught.exception))
                self.assertNotIn("test-gemini-secret", str(caught.exception))
        self.sdk.assert_not_called()

    def test_actual_sdk_configuration_has_no_retries_and_exact_environment_model(self):
        with patch.dict(os.environ, {"LLM_BASE_URL": GEMINI_BASE_URL + "/"}):
            client = from_environment()
        settings = self.sdk.call_args.kwargs
        self.assertEqual(settings["api_key"], "test-gemini-secret")
        self.assertEqual(settings["base_url"], GEMINI_BASE_URL + "/")
        self.assertEqual(settings["max_retries"], 0)
        self.assertEqual(settings["timeout"], TIMEOUT_SECONDS)
        self.assertEqual(settings["default_headers"], {"Accept-Encoding": "identity"})
        self.assertFalse(self.http.call_args.kwargs["follow_redirects"])
        self.assertFalse(self.http.call_args.kwargs["trust_env"])
        self.assertEqual(client.name, "gemini/gemini-exact-configured-model")
        self.assertNotIn("test-gemini-secret", repr(client))

    def test_invalid_keys_and_missing_sdk_fail_without_echoing_values(self):
        for key in ("private key", "private\nkey", "secrét", "x" * 4097):
            with patch.dict(os.environ, {"LLM_API_KEY": key}):
                with self.assertRaises(RuntimeModelError) as caught:
                    from_environment()
                self.assertNotIn(key, str(caught.exception))
        with patch("app.runtime.model_client.OpenAI", None):
            with self.assertRaisesRegex(RuntimeModelError, "SDK is unavailable"):
                from_environment()

    def test_constructor_failures_are_sanitized_and_client_closed(self):
        self.sdk.side_effect = ValueError("test-gemini-secret private source text")
        with self.assertRaises(RuntimeModelError) as caught:
            from_environment()
        self.assertNotIn("test-gemini-secret", str(caught.exception))
        self.assertNotIn("private source text", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        self.http.return_value.close.assert_called_once()

    def test_json_call_and_safe_stage_metadata(self):
        client = from_environment()
        client.stage = "investigator"
        self.sdk.return_value.chat.completions.create.return_value = sdk_response('{"plans":[]}')
        self.assertEqual(client.complete_json("Discover plans.", {"evidence": []}), {"plans": []})
        body = self.sdk.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(body["model"], "gemini-exact-configured-model")
        self.assertEqual(body["max_tokens"], MAX_OUTPUT_TOKENS)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertFalse(body["stream"])
        self.assertEqual(json.loads(body["messages"][1]["content"]), {"evidence": []})
        self.assertEqual(len(client.calls), 1)
        metadata = client.calls[0]
        self.assertEqual(metadata["stage"], "investigator")
        self.assertEqual(metadata["status"], "success")
        self.assertEqual(metadata["provider"], "gemini")
        self.assertEqual(metadata["response_id"], "chatcmpl-test")
        self.assertEqual(metadata["usage"]["total_tokens"], 150)
        self.assertIsInstance(metadata["duration_ms"], int)
        self.assertNotIn("Discover plans", json.dumps(metadata))
        self.assertNotIn("test-gemini-secret", json.dumps(metadata))
        client.complete_json("Review.", {}, stage="red_team")
        self.assertEqual(client.calls[-1]["stage"], "red_team")

    def test_request_limit_and_invalid_input_block_network(self):
        client = from_environment()
        for prompt, payload in (("", {}), ("Plan.", []), ("Plan.", {"x": float("nan")}), ("Plan.", {"x": object()}), ("Plan.", {"x": "x" * MAX_REQUEST_BYTES})):
            with self.assertRaises(RuntimeModelError):
                client.complete_json(prompt, payload)
        self.sdk.return_value.chat.completions.create.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_invalid_json_rejected_including_duplicates_and_nonfinite_values(self):
        client = from_environment()
        invalid = ["not-json", "[]", "null", '```json\n{}\n```', '{"x":NaN}', '{"x":1e1000}', '{"x":1,"x":2}']
        for content in invalid:
            with self.subTest(content=content):
                self.sdk.return_value.chat.completions.create.return_value = sdk_response(content)
                with self.assertRaises(RuntimeModelError):
                    client.complete_json("Plan.", {})
                self.assertEqual(client.calls[-1]["status"], "invalid_response")

    def test_truncated_refused_tool_or_malformed_responses_fail_closed(self):
        client = from_environment()
        responses = [sdk_response(finish_reason="length"), sdk_response(content=None), sdk_response(content=""), SimpleNamespace(choices=[]), SimpleNamespace(choices=None)]
        for field_name, field_value in (("refusal", "private refusal"), ("tool_calls", [{}]), ("function_call", {"name": "execute"})):
            response = sdk_response()
            setattr(response.choices[0].message, field_name, field_value)
            responses.append(response)
        for response in responses:
            self.sdk.return_value.chat.completions.create.return_value = response
            with self.assertRaises(RuntimeModelError):
                client.complete_json("Plan.", {})
        self.sdk.return_value.chat.completions.create.return_value = sdk_response("x" * (MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(RuntimeModelError, "byte limit"):
            client.complete_json("Plan.", {})

    def test_sdk_exception_not_retried_or_logged_and_safe_error_metadata(self):
        client = from_environment()
        self.sdk.return_value.chat.completions.create.side_effect = Exception("test-gemini-secret private financial text")
        output = io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", output):
            with self.assertRaises(RuntimeModelError) as caught:
                client.complete_json("private financial text", {}, stage="repair")
        self.sdk.return_value.chat.completions.create.assert_called_once()
        self.assertTrue(caught.exception.__suppress_context__)
        rendered = str(caught.exception) + output.getvalue() + json.dumps(client.calls)
        self.assertNotIn("test-gemini-secret", rendered)
        self.assertNotIn("private financial text", rendered)
        self.assertEqual(client.calls[0]["status"], "error")
        self.assertIsNone(client.calls[0]["response_id"])

    def test_sdk_cannot_escape_sanitization_with_runtime_error_type(self):
        client = from_environment()
        self.sdk.return_value.chat.completions.create.side_effect = RuntimeModelError("test-gemini-secret")
        with self.assertRaises(RuntimeModelError) as caught:
            client.complete_json("Plan.", {})
        self.assertNotIn("test-gemini-secret", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_concurrent_calls_keep_per_request_stage_and_response_metadata(self):
        client = from_environment()
        barrier = threading.Barrier(2)

        def respond(**kwargs):
            label = json.loads(kwargs["messages"][1]["content"])["label"]
            barrier.wait(timeout=3)
            return sdk_response(json.dumps({"label": label}), response_id="response-" + label)

        self.sdk.return_value.chat.completions.create.side_effect = respond
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(client.complete_json, "Plan.", {"label": stage}, stage=stage) for stage in ("contract_discovery", "relationship_discovery")]
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual({result["label"] for result in results}, {"contract_discovery", "relationship_discovery"})
        self.assertEqual(len(client.calls), 2)
        for call in client.calls:
            self.assertEqual(call["response_id"], "response-" + call["stage"])
            self.assertEqual(call["status"], "success")
        self.assertEqual(client.stage, "unspecified")

    def test_untrusted_metadata_cannot_include_credentials_or_response_text(self):
        client = from_environment()
        response = sdk_response(response_id="id-test-gemini-secret")
        response.usage = SimpleNamespace(prompt_tokens=True, completion_tokens="private", total_tokens=-1)
        self.sdk.return_value.chat.completions.create.return_value = response
        client.complete_json("Plan.", {}, stage="test-gemini-secret")
        self.assertEqual(client.calls[0]["stage"], "unspecified")
        self.assertIsNone(client.calls[0]["response_id"])
        self.assertEqual(client.calls[0]["usage"], {})

    def test_close_failures_are_sanitized(self):
        client = from_environment()
        self.sdk.return_value.close.side_effect = Exception("test-gemini-secret")
        with self.assertRaises(RuntimeModelError) as caught:
            client.close()
        self.assertNotIn("test-gemini-secret", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


class ResponseBoundsTest(unittest.TestCase):
    def test_stream_stops_at_byte_limit_and_closes_underlying_stream(self):
        stream = MagicMock()
        stream.__iter__.return_value = iter([b"a" * MAX_RESPONSE_BYTES, b"b"])
        bounded = _BoundedStream(stream)
        iterator = iter(bounded)
        self.assertEqual(len(next(iterator)), MAX_RESPONSE_BYTES)
        with self.assertRaisesRegex(RuntimeModelError, "byte limit"):
            next(iterator)
        bounded.close()
        stream.close.assert_called_once()

    def test_stream_deadline(self):
        with patch("app.runtime.model_client.time.monotonic", side_effect=[0, TIMEOUT_SECONDS + 1]):
            with self.assertRaisesRegex(RuntimeModelError, "time limit"):
                list(_BoundedStream(iter([b"{}"])) )

    def test_content_length_and_compression_rejected_before_buffering(self):
        for headers in ({"content-length": str(MAX_RESPONSE_BYTES + 1)}, {"content-encoding": "gzip"}):
            with self.assertRaises(RuntimeModelError):
                _bound_response(SimpleNamespace(headers=headers, stream=iter([])))

    def test_real_sdk_mock_transport_uses_google_url_and_cannot_follow_redirects(self):
        import httpx2
        from openai import DefaultHttpxClient, OpenAI

        requests = []

        def respond(request):
            requests.append(request)
            return httpx2.Response(302, headers={"Location": "https://elsewhere.invalid/"}, stream=httpx2.ByteStream(b""))

        http_client = DefaultHttpxClient(transport=httpx2.MockTransport(respond), follow_redirects=False, event_hooks={"response": [_bound_response]})
        sdk = OpenAI(api_key="test-gemini-secret", base_url=GEMINI_BASE_URL, max_retries=0, http_client=http_client)
        client = GeminiClient(model="gemini-exact-test", _sdk=sdk, _api_key="test-gemini-secret")
        try:
            with self.assertRaises(RuntimeModelError):
                client.complete_json("Plan.", {})
            self.assertEqual(len(requests), 1)
            self.assertEqual(str(requests[0].url), GEMINI_BASE_URL + "/chat/completions")
        finally:
            client.close()

    def test_real_sdk_successful_json_parse_records_exact_request_and_usage(self):
        import httpx2
        from openai import DefaultHttpxClient, OpenAI

        requests = []

        def respond(request):
            requests.append(request)
            body = {
                "id": "chatcmpl-local-test",
                "object": "chat.completion",
                "created": 0,
                "model": "gemini-exact-test",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"plans":[]}'}}],
                "usage": {"prompt_tokens": 35, "completion_tokens": 15, "total_tokens": 50},
            }
            return httpx2.Response(200, headers={"Content-Type": "application/json"}, stream=httpx2.ByteStream(json.dumps(body).encode()))

        http_client = DefaultHttpxClient(transport=httpx2.MockTransport(respond), follow_redirects=False, event_hooks={"response": [_bound_response]})
        sdk = OpenAI(api_key="test-gemini-secret", base_url=GEMINI_BASE_URL, max_retries=0, http_client=http_client)
        client = GeminiClient(model="gemini-exact-test", _sdk=sdk, _api_key="test-gemini-secret")
        try:
            self.assertEqual(client.complete_json("Plan.", {}, stage="investigator"), {"plans": []})
            self.assertEqual(len(requests), 1)
            body = json.loads(requests[0].content)
            self.assertEqual(body["model"], "gemini-exact-test")
            self.assertEqual(body["max_tokens"], MAX_OUTPUT_TOKENS)
            self.assertEqual(client.calls[0]["status"], "success")
            self.assertEqual(client.calls[0]["response_id"], "chatcmpl-local-test")
            self.assertEqual(client.calls[0]["usage"]["total_tokens"], 50)
        finally:
            client.close()

    def test_real_sdk_enforces_chunked_error_body_limit(self):
        import httpx2
        from openai import DefaultHttpxClient, OpenAI

        chunks_read = []

        class OversizedStream(httpx2.SyncByteStream):
            def __iter__(self):
                for index in range(4):
                    chunks_read.append(index)
                    yield b"x" * (MAX_RESPONSE_BYTES // 2)

        def respond(request):
            return httpx2.Response(400, stream=OversizedStream())

        http_client = DefaultHttpxClient(transport=httpx2.MockTransport(respond), follow_redirects=False, event_hooks={"response": [_bound_response]})
        sdk = OpenAI(api_key="test-gemini-secret", base_url=GEMINI_BASE_URL, max_retries=0, http_client=http_client)
        client = GeminiClient(model="gemini-exact-test", _sdk=sdk, _api_key="test-gemini-secret")
        try:
            with self.assertRaises(RuntimeModelError):
                client.complete_json("Plan.", {})
            self.assertEqual(chunks_read, [0, 1, 2])
            self.assertEqual(client.calls[-1]["status"], "error")
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
