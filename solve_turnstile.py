"""Solve a Cloudflare Turnstile widget with the ZeroCaptcha API and print its token.

    export ZEROCAPTCHA_API=https://api.zerocaptcha.io   # the API's address, from the docs
    export ZEROCAPTCHA_KEY=zc_live_...               # your API key, from the dashboard
    python solve_turnstile.py https://shop.example.com/login 0x4AAAAAAAB1cD2eF3gH4iJ5 [action] [cdata]

action and cdata are the widget's data-action and data-cdata (or turnstile.render()'s action and
cData options): pass them whenever the widget sets them, since many sites check both when they
verify the token.

Standard library only; Python 3.9 or later. Import solve_turnstile() to use it in your own code.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

# Answers worth another try after a wait: too many requests, a server busy or away, and the
# first request with this Idempotency-Key still being served (409 idempotency_key_in_use).
RETRYABLE = {429, 502, 503, 504}
ATTEMPTS = 3  # tries per request, in all
REQUEST_SECONDS = 30  # the longest one HTTP request may take


class ZeroCaptchaError(Exception):
    """The API refused a request, the task ended without a token, or the wait ran out."""

    def __init__(self, code: str, message: str, request_id: Optional[str] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.request_id = request_id


def solve_turnstile(
    api: str,
    key: str,
    website_url: str,
    website_key: str,
    *,
    action: Optional[str] = None,
    cdata: Optional[str] = None,
    proxy: Optional[str] = None,
    timeout: float = 180,
    interval: float = 2,
) -> str:
    """Creates a Cloudflare Turnstile task, waits for it, and returns the token.

    The token works once, for 300 seconds: use it straight away. A task that fails or expires
    raises ZeroCaptchaError with its errorCode, and nothing is charged.
    """
    deadline = time.monotonic() + timeout
    task: Dict[str, Any] = {
        "type": "TurnstileTask" if proxy else "TurnstileTaskProxyless",
        "websiteURL": website_url,
        "websiteKey": website_key,
    }
    if action:
        task["action"] = action
    if cdata:
        task["cdata"] = cdata
    if proxy:
        task["proxy"] = proxy  # such as http://user:pass@proxy.example.net:8080
    # One key per task: a retry after a lost reply returns this task instead of making another.
    current = _request(api, key, "POST", "/v1/tasks", deadline, task, str(uuid.uuid4()))
    while current["status"] in ("queued", "running"):
        if time.monotonic() + interval >= deadline:
            raise ZeroCaptchaError(
                "timeout", f"Task {current['id']} was still {current['status']} at the deadline."
            )
        time.sleep(interval)
        current = _request(api, key, "GET", f"/v1/tasks/{current['id']}", deadline)
    token = (current.get("solution") or {}).get("token")
    if current["status"] == "succeeded" and token:
        return token
    raise ZeroCaptchaError(
        current.get("errorCode") or current["status"],
        current.get("errorDescription") or f"The task {current['status']}; nothing was charged.",
    )


def _request(
    api: str,
    key: str,
    method: str,
    path: str,
    deadline: float,
    body: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Sends one request, trying it up to ATTEMPTS times with the same Idempotency-Key."""
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    for attempt in range(1, ATTEMPTS + 1):
        left = deadline - time.monotonic()
        if left <= 0:
            raise ZeroCaptchaError("timeout", f"{method} {path} ran past the deadline.")
        request = urllib.request.Request(
            api.rstrip("/") + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=min(REQUEST_SECONDS, left)) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            refusal = _refusal(error)
            if not _retryable(error.code, refusal.code) or attempt == ATTEMPTS:
                raise refusal from None
            wait = _retry_after(error.headers.get("Retry-After"), attempt)
        except (urllib.error.URLError, OSError, ValueError) as error:
            # No answer, or one cut short: the same Idempotency-Key makes a retry safe.
            if attempt == ATTEMPTS:
                raise ZeroCaptchaError("network", str(error)) from None
            wait = float(attempt)
        if time.monotonic() + wait >= deadline:
            raise ZeroCaptchaError("timeout", f"{method} {path} ran past the deadline.")
        time.sleep(wait)
    raise AssertionError("unreachable")


def _retryable(status: int, code: str) -> bool:
    return status in RETRYABLE or (status == 409 and code == "idempotency_key_in_use")


def _refusal(error: urllib.error.HTTPError) -> ZeroCaptchaError:
    """The API's problem document (RFC 9457) as an error: its code, detail and request ID."""
    try:
        problem = json.loads(error.read())
    except ValueError:
        problem = {}
    if not isinstance(problem, dict):
        problem = {}
    return ZeroCaptchaError(
        str(problem.get("code") or f"http_{error.code}"),
        str(problem.get("detail") or problem.get("title") or f"HTTP {error.code}"),
        problem.get("request_id") or error.headers.get("x-request-id"),
    )


def _retry_after(value: Optional[str], attempt: int) -> float:
    """The wait a Retry-After header asks for in seconds, or a pause that grows each attempt."""
    if value is not None and value.strip().isdigit():
        return float(value.strip())
    return float(attempt)


def main(argv: list) -> int:
    if len(argv) not in (3, 4, 5):
        print(__doc__, file=sys.stderr)
        return 2
    api, key = os.environ.get("ZEROCAPTCHA_API"), os.environ.get("ZEROCAPTCHA_KEY")
    if not api or not key:
        print("Set ZEROCAPTCHA_API and ZEROCAPTCHA_KEY first.", file=sys.stderr)
        return 2
    try:
        token = solve_turnstile(
            api,
            key,
            argv[1],
            argv[2],
            action=argv[3] if len(argv) >= 4 else None,
            cdata=argv[4] if len(argv) == 5 else None,
            proxy=os.environ.get("PROXY_URL") or None,
        )
    except ZeroCaptchaError as error:
        request = f" (request {error.request_id})" if error.request_id else ""
        print(f"{error}{request}", file=sys.stderr)
        return 1
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
