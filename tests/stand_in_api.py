"""A stand-in for the ZeroCaptcha REST API on this machine, so the tests make no real task.

It answers POST /v1/tasks and GET /v1/tasks/{id} as the API does, records every request, and
plays one scenario:

- "success": the task runs on the first poll and succeeds on the next.
- "failed": the task fails with ERROR_CAPTCHA_UNSOLVABLE.
- "rate-limited": the first create is answered 429 with Retry-After: 0, then as "success".
- "insufficient-funds": every create is refused 402 with the code insufficient_funds.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

KEY = "zc_live_test_key"
TASK_ID = "0192f3a4-7b1c-7d2e-9f10-3c4d5e6f7a8b"
TOKEN = "0.stand-in-turnstile-token"


class StandInApi:
    def __init__(self, scenario: str = "success") -> None:
        self.scenario = scenario
        self.requests: List[Dict[str, Any]] = []
        self.creates = 0
        self.polls = 0
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:  # keep the test output clean
                pass

            def do_POST(self) -> None:  # noqa: N802 - the name http.server calls
                stand_in.handle(self, "POST")

            def do_GET(self) -> None:  # noqa: N802
                stand_in.handle(self, "GET")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "StandInApi":
        self.thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()

    def handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        body = json.loads(raw) if raw else None
        self.requests.append(
            {
                "method": method,
                "path": handler.path,
                "authorization": handler.headers.get("Authorization"),
                "idempotency_key": handler.headers.get("Idempotency-Key"),
                "body": body,
            }
        )
        if handler.headers.get("Authorization") != f"Bearer {KEY}":
            return self.problem(handler, 401, "unauthorized", "The API key is not valid.")
        if method == "POST" and handler.path == "/v1/tasks":
            return self.create(handler, body)
        if method == "GET" and handler.path == f"/v1/tasks/{TASK_ID}":
            return self.poll(handler)
        return self.problem(handler, 404, "not_found", "No such route.")

    def create(self, handler: BaseHTTPRequestHandler, body: Any) -> None:
        self.creates += 1
        if not isinstance(body, dict) or not body.get("websiteURL") or not body.get("websiteKey"):
            return self.problem(handler, 422, "validation_failed", "websiteURL and websiteKey.")
        if self.scenario == "rate-limited" and self.creates == 1:
            return self.problem(handler, 429, "rate_limited", "Slow down.", {"Retry-After": "0"})
        if self.scenario == "insufficient-funds":
            return self.problem(handler, 402, "insufficient_funds", "Add funds and try again.")
        self.reply(handler, 201, self.task("queued", body))

    def poll(self, handler: BaseHTTPRequestHandler) -> None:
        self.polls += 1
        if self.scenario == "failed":
            task = self.task("failed")
            task["errorCode"] = "ERROR_CAPTCHA_UNSOLVABLE"
            task["errorDescription"] = "Every attempt failed. Nothing was charged."
            return self.reply(handler, 200, task)
        if self.polls == 1:
            return self.reply(handler, 200, self.task("running"))
        task = self.task("succeeded")
        task["solution"] = {"token": TOKEN}
        task["cost"] = "0.001000"
        self.reply(handler, 200, task)

    @staticmethod
    def task(status: str, body: Any = None) -> Dict[str, Any]:
        body = body or {}
        return {
            "id": TASK_ID,
            "type": body.get("type", "TurnstileTaskProxyless"),
            "kind": "turnstile",
            "status": status,
            "websiteURL": body.get("websiteURL", "https://shop.example.com/login"),
            "websiteKey": body.get("websiteKey", "0x4AAAAAAAB1cD2eF3gH4iJ5"),
            "price": "0.001000",
            "held": "0.001000" if status in ("queued", "running") else "0.000000",
            "cost": "0.000000",
            "createdAt": "2026-09-30T12:00:00Z",
        }

    @staticmethod
    def reply(handler: BaseHTTPRequestHandler, status: int, body: Any, headers: Any = None) -> None:
        data = json.dumps(body).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            handler.send_header(name, value)
        handler.end_headers()
        handler.wfile.write(data)

    def problem(
        self,
        handler: BaseHTTPRequestHandler,
        status: int,
        code: str,
        detail: str,
        headers: Any = None,
    ) -> None:
        self.reply(
            handler,
            status,
            {
                "type": f"https://zerocaptcha.io/docs/reference/errors#{code}",
                "title": code.replace("_", " ").capitalize(),
                "status": status,
                "detail": detail,
                "code": code,
                "request_id": "0192f3a4-0000-7000-8000-000000000000",
            },
            headers,
        )
