"""Exercise the implemented API through ASGI without optional test clients.

The repository currently implements a health endpoint only. These tests do not
treat the synthetic pipeline snapshot as a running application.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from app.main import app


async def request(method: str, path: str) -> tuple[int, dict[str, str], bytes]:
    """Send one complete HTTP request to the real FastAPI application."""
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    response = next(item for item in messages if item["type"] == "http.response.start")
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in response["headers"]
    }
    body = b"".join(
        item.get("body", b"") for item in messages if item["type"] == "http.response.body"
    )
    return response["status"], headers, body


class ImplementedApiQaTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_is_successful_json(self) -> None:
        status, headers, body = await request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["content-type"])
        self.assertEqual(json.loads(body), {"status": "ok"})

    async def test_unknown_resource_is_json_without_traceback(self) -> None:
        status, headers, body = await request("GET", "/qa-resource-that-does-not-exist")
        self.assertEqual(status, 404)
        self.assertIn("application/json", headers["content-type"])
        self.assertEqual(json.loads(body), {"detail": "Not Found"})
        self.assertNotIn(b"Traceback", body)

    async def test_unsupported_health_method_is_json_without_traceback(self) -> None:
        status, headers, body = await request("POST", "/health")
        self.assertEqual(status, 405)
        self.assertIn("GET", headers["allow"])
        self.assertEqual(json.loads(body), {"detail": "Method Not Allowed"})
        self.assertNotIn(b"Traceback", body)

    async def test_openapi_is_parseable_and_documents_health(self) -> None:
        status, _, body = await request("GET", "/openapi.json")
        self.assertEqual(status, 200)
        schema = json.loads(body)
        self.assertEqual(schema["info"]["title"], "CrazyMonkey API")
        self.assertIn("200", schema["paths"]["/health"]["get"]["responses"])

    async def test_builtin_documentation_pages_return_html(self) -> None:
        for path in ("/docs", "/docs/oauth2-redirect", "/redoc"):
            with self.subTest(path=path):
                status, headers, body = await request("GET", path)
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["content-type"])
                self.assertIn(b"<html", body.lower())


if __name__ == "__main__":
    unittest.main()
