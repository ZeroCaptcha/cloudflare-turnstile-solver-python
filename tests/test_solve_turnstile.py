"""solve_turnstile.py against a stand-in API: no key, no real task, nothing spent."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from solve_turnstile import ZeroCaptchaError, solve_turnstile
from stand_in_api import KEY, TOKEN, StandInApi

PAGE = "https://shop.example.com/login"
SITEKEY = "0x4AAAAAAAB1cD2eF3gH4iJ5"


class SolveTurnstileTest(unittest.TestCase):
    def test_returns_the_token(self) -> None:
        with StandInApi("success") as api:
            token = solve_turnstile(
                api.url, KEY, PAGE, SITEKEY, action="login", cdata="session-7f3a9c2e", interval=0.01
            )
        self.assertEqual(token, TOKEN)
        create = api.requests[0]
        self.assertEqual((create["method"], create["path"]), ("POST", "/v1/tasks"))
        self.assertEqual(create["authorization"], f"Bearer {KEY}")
        self.assertTrue(create["idempotency_key"])
        self.assertEqual(
            create["body"],
            {
                "type": "TurnstileTaskProxyless",
                "websiteURL": PAGE,
                "websiteKey": SITEKEY,
                # The widget's action and cData reach the API, so a site that checks them accepts it.
                "action": "login",
                "cdata": "session-7f3a9c2e",
            },
        )
        self.assertEqual([r["method"] for r in api.requests], ["POST", "GET", "GET"])

    def test_a_proxy_makes_a_proxied_task(self) -> None:
        proxy = "http://user:pass@proxy.example.net:8080"
        with StandInApi("success") as api:
            solve_turnstile(api.url, KEY, PAGE, SITEKEY, proxy=proxy, interval=0.01)
        self.assertEqual(api.requests[0]["body"]["type"], "TurnstileTask")
        self.assertEqual(api.requests[0]["body"]["proxy"], proxy)

    def test_a_failed_task_raises_its_code(self) -> None:
        with StandInApi("failed") as api, self.assertRaises(ZeroCaptchaError) as raised:
            solve_turnstile(api.url, KEY, PAGE, SITEKEY, interval=0.01)
        self.assertEqual(raised.exception.code, "ERROR_CAPTCHA_UNSOLVABLE")

    def test_a_rate_limited_create_is_retried_with_the_same_key(self) -> None:
        with StandInApi("rate-limited") as api:
            token = solve_turnstile(api.url, KEY, PAGE, SITEKEY, interval=0.01)
        self.assertEqual(token, TOKEN)
        creates = [r for r in api.requests if r["method"] == "POST"]
        self.assertEqual(len(creates), 2)
        self.assertEqual(creates[0]["idempotency_key"], creates[1]["idempotency_key"])

    def test_a_refusal_is_raised_at_once(self) -> None:
        with StandInApi("insufficient-funds") as api, self.assertRaises(ZeroCaptchaError) as raised:
            solve_turnstile(api.url, KEY, PAGE, SITEKEY, interval=0.01)
        self.assertEqual(raised.exception.code, "insufficient_funds")
        self.assertTrue(raised.exception.request_id)
        self.assertEqual(len(api.requests), 1)

    def test_the_deadline_stops_the_wait(self) -> None:
        with StandInApi("success") as api, self.assertRaises(ZeroCaptchaError) as raised:
            solve_turnstile(api.url, KEY, PAGE, SITEKEY, timeout=0.5, interval=1)
        self.assertEqual(raised.exception.code, "timeout")

    def test_the_command_prints_the_token(self) -> None:
        script = Path(__file__).resolve().parent.parent / "solve_turnstile.py"
        with StandInApi("success") as api:
            run = subprocess.run(
                [sys.executable, str(script), PAGE, SITEKEY, "login", "session-7f3a9c2e"],
                env={**os.environ, "ZEROCAPTCHA_API": api.url, "ZEROCAPTCHA_KEY": KEY},
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), TOKEN)
        self.assertEqual(api.requests[0]["body"]["action"], "login")
        self.assertEqual(api.requests[0]["body"]["cdata"], "session-7f3a9c2e")


if __name__ == "__main__":
    unittest.main()
