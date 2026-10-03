<!-- zc:header (generated from the registry; edit repos/registry.json) -->
# Cloudflare Turnstile CAPTCHA solver in Python

[![CI](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-python/actions/workflows/ci.yml/badge.svg)](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-python/actions/workflows/ci.yml)

Solve Cloudflare Turnstile in Python: a small, tested example that sends the page URL and sitekey to the ZeroCaptcha API and returns a Cloudflare Turnstile token. Standard library only, Python 3.9+, with retries, idempotency keys and a deadline.

[Website](https://zerocaptcha.io/cloudflare-turnstile-solver/python) · [Docs](https://zerocaptcha.io/docs) · [Quickstart](https://zerocaptcha.io/docs/quickstart) · [API reference](https://zerocaptcha.io/docs/reference/api) · [Pricing](https://zerocaptcha.io/pricing)
<!-- /zc:header -->

## What it does

`solve_turnstile.py` gets a valid Cloudflare Turnstile token for a page you are allowed to automate. You give it the page's URL and the widget's sitekey; it creates a task on the ZeroCaptcha API, waits for it, and returns the token for you to submit as the browser would.

- **Standard library only:** `urllib`, `json` and `uuid`. Python 3.9 or later, nothing to install.
- **Safe to retry:** every task is created with its own `Idempotency-Key`, so a retry after a lost reply returns the same task instead of paying for a second one.
- **Waits sensibly:** polls every 2 seconds, retries 429, 502, 503 and 504 after the wait the API asks for, and stops at a deadline you set (3 minutes by default).
- **Clear failures:** a refusal or a failed task raises `ZeroCaptchaError` with the API's code, such as `insufficient_funds` or `ERROR_CAPTCHA_UNSOLVABLE`, and the request ID to quote to support.

## Quickstart

1. Create an account on the ZeroCaptcha website, create an API key on the dashboard and add funds (crypto, from $10). A task is charged only when it succeeds.
2. Put the API's address and your key in your environment, never in your code:

   ```sh
   export ZEROCAPTCHA_API=https://api.zerocaptcha.io
   export ZEROCAPTCHA_KEY=zc_live_...
   ```

3. Find the widget's sitekey: the `data-sitekey` attribute of the Cloudflare Turnstile element on the page (the [sitekey guide](https://zerocaptcha.io/guides/find-cloudflare-turnstile-sitekey) shows where else it hides), and its `data-action` and `data-cdata` if it sets them (or the `action` and `cData` options of `turnstile.render()`). Many sites check both when they verify the token.
4. Run it:

   ```sh
   python solve_turnstile.py https://shop.example.com/login 0x4AAAAAAAB1cD2eF3gH4iJ5 login session-7f3a9c2e
   ```

   It prints the token. Set `PROXY_URL=http://user:pass@proxy.example.net:8080` to solve through your own proxy.

## Use it in your code

```python
import os

from solve_turnstile import ZeroCaptchaError, solve_turnstile

try:
    token = solve_turnstile(
        os.environ["ZEROCAPTCHA_API"],
        os.environ["ZEROCAPTCHA_KEY"],
        "https://shop.example.com/login",
        "0x4AAAAAAAB1cD2eF3gH4iJ5",
        # The widget's data-action and data-cdata, or turnstile.render()'s action and cData
        # options; leave out any the widget does not set.
        action="login",
        cdata="session-7f3a9c2e",
        # proxy="http://user:pass@proxy.example.net:8080",  # to solve through your own proxy
    )
except ZeroCaptchaError as error:
    print(error.code, error.request_id)
    raise
```

## Submit the token

The widget puts its token in a form field named `cf-turnstile-response`; the site checks it with Cloudflare's siteverify when the form arrives. Send yours the same way, straight after you get it:

```python
import urllib.parse
import urllib.request

form = urllib.parse.urlencode(
    {"email": "me@example.com", "password": "...", "cf-turnstile-response": token}
).encode()
with urllib.request.urlopen("https://shop.example.com/login", data=form, timeout=30) as response:
    print(response.status)
```

With `requests`, `httpx` or Scrapy it is the same field: see the [httpx and requests tutorial](https://zerocaptcha.io/blog/python-httpx-cloudflare-turnstile) and the [Scrapy tutorial](https://zerocaptcha.io/blog/scrapy-cloudflare-turnstile).

## How it works

1. `POST /v1/tasks` with the page, the sitekey, and the action and cData if the widget sets them. The task's price is held on your balance.
2. `GET /v1/tasks/{id}` every 2 seconds while the task is `queued` or `running`.
3. `succeeded` carries `solution.token`, and the held price is charged. `failed` or `expired` carries an `errorCode`, and the hold is released: nothing is charged.

The [task lifecycle](https://zerocaptcha.io/docs/how-tasks-work) and the [errors and retries guide](https://zerocaptcha.io/docs/errors-and-retries) have every detail.

## Honest limits

- **A token works once, for 300 seconds.** Get it just before you submit the form, and get a new one for the next submission.
- **The action and cData must match the widget's.** A token made without them can be refused by the site's siteverify check.
- **Proxies are `http` or `https`,** with the port in the URL. SOCKS is not supported.
- **Only for sites you own or are allowed to automate.** The [Acceptable Use Policy](https://zerocaptcha.io/legal/acceptable-use) applies to every task.
- **This is an example, not a library.** For a maintained client with callbacks and signature checks, use the official [Python SDK](https://github.com/ZeroCaptcha/zerocaptcha-python).

## FAQ

**Does it work with requests, httpx, Scrapy or Playwright?**
Yes. The solver returns a string; each of those sends it in the `cf-turnstile-response` field. For browsers, see the [Selenium](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-selenium) and [Playwright](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-playwright) examples.

**What does a solve cost?**
The [pricing page](https://zerocaptcha.io/pricing) lists the price per 1,000 solved tasks. Only a task that succeeds is charged; a failed or expired one costs nothing.

**How long does a solve take?**
It varies with the site and the load. The [status page](https://zerocaptcha.io/status) shows the live figures for the last 24 hours.

**Why is my token refused by the site?**
Most often it was used twice, used after 300 seconds, or made without the widget's action or cData. The [siteverify errors article](https://zerocaptcha.io/blog/cloudflare-turnstile-siteverify-errors) explains each code.

**Can I use the 2Captcha or createTask formats instead?**
Yes: the same API answers `in.php` and `createTask`. See [createtask-api-migration](https://github.com/ZeroCaptcha/createtask-api-migration).

## Run the tests

```sh
python -m unittest discover -s tests -v
```

The tests run `solve_turnstile.py` against a stand-in API on your machine: no key, no real task, nothing spent.

<!-- zc:footer (generated from the registry) -->
## More from ZeroCaptcha

- The website: [ZeroCaptcha](https://zerocaptcha.io), the [docs](https://zerocaptcha.io/docs), the [guides](https://zerocaptcha.io/guides), the [blog](https://zerocaptcha.io/blog) and the [status page](https://zerocaptcha.io/status)
- Start here: [zerocaptcha](https://github.com/ZeroCaptcha/zerocaptcha), [cloudflare-turnstile-solver](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver), [cloudflare-challenge-solver](https://github.com/ZeroCaptcha/cloudflare-challenge-solver)
- Examples by language: **cloudflare-turnstile-solver-python**, [cloudflare-turnstile-solver-nodejs](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-nodejs), [cloudflare-turnstile-solver-go](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-go), [cloudflare-turnstile-solver-php](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-php), [cloudflare-turnstile-solver-java](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-java), [cloudflare-turnstile-solver-csharp](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-csharp), [cloudflare-turnstile-solver-rust](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-rust)
- Browser automation: [cloudflare-turnstile-solver-playwright](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-playwright), [cloudflare-turnstile-solver-puppeteer](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-puppeteer), [cloudflare-turnstile-solver-selenium](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-selenium)
- SDKs, MCP server and migration: [zerocaptcha-js](https://github.com/ZeroCaptcha/zerocaptcha-js), [zerocaptcha-python](https://github.com/ZeroCaptcha/zerocaptcha-python), [zerocaptcha-go](https://github.com/ZeroCaptcha/zerocaptcha-go), [zerocaptcha-mcp](https://github.com/ZeroCaptcha/zerocaptcha-mcp), [createtask-api-migration](https://github.com/ZeroCaptcha/createtask-api-migration)
- Lists: [awesome-cloudflare-turnstile](https://github.com/ZeroCaptcha/awesome-cloudflare-turnstile)

## Licence

MIT: see [LICENSE](LICENSE).

## Disclaimer

ZeroCaptcha is an independent service, not affiliated with or endorsed by Cloudflare. Cloudflare and Turnstile are trademarks of Cloudflare, Inc. Use ZeroCaptcha only on sites you own or are allowed to automate, as the [Acceptable Use Policy](https://zerocaptcha.io/legal/acceptable-use) says; any site owner can [opt out](https://zerocaptcha.io/opt-out).
<!-- /zc:footer -->
