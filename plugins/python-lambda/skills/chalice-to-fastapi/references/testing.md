# Testing: a TestClient shim

Chalice test suites typically build a raw API Gateway Lambda event, call the app as a
handler (`app(event, context)`), and assert on `response["statusCode"]`, `response["body"]`
(a JSON string) and `response["headers"]`. To avoid rewriting every test file,
**reimplement the two test-facing helpers as a shim over FastAPI's `TestClient`**. Keep
their names and call shapes, change only their bodies. Below they are called `make_event`
and `call_app`; use the names your suite already has.

## conftest.py

```python
import json
from contextlib import suppress

from fastapi import FastAPI
from fastapi.testclient import TestClient   # needs httpx (add it to dev deps)
from pytest import fixture


@fixture
def make_event():
    """Describe a request. Same name and shape as the old Chalice event builder;
    call_app below actually executes it."""
    def make(uri, method, path=None, query=None, body=None,
             content_type="application/json", token=None, headers=None):
        return {"uri": uri, "method": method, "path": path or {}, "query": query,
                "body": body, "content_type": content_type,
                "token": token, "headers": headers}
    return make


_CLIENTS: dict = {}


def _client(app_or_module) -> TestClient:
    app = app_or_module if isinstance(app_or_module, FastAPI) else app_or_module.app
    if id(app) not in _CLIENTS:
        _CLIENTS[id(app)] = TestClient(app, raise_server_exceptions=False)
    return _CLIENTS[id(app)]


@fixture
def call_app():
    def process(event, handler):           # handler == the imported FastAPI `app`
        client = _client(handler)
        url = event["uri"].format(**event["path"])   # /x/{id} + {"id": 1} -> /x/1
        headers = {}
        if event["token"] is not None:
            headers["Authorization"] = event["token"]   # use your real auth header
        if event["body"] is not None:
            headers["Content-Type"] = event["content_type"]
        if event["headers"]:
            headers.update(event["headers"])
        raw = client.request(event["method"], url, params=event["query"],
                             content=event["body"], headers=headers)
        response = {
            "statusCode": raw.status_code,
            "headers": raw.headers,          # httpx.Headers is case-INSENSITIVE, so
            "body": raw.text,                # ["Content-Type"] and .get("Access-...") both work
        }
        with suppress(json.JSONDecodeError, UnicodeDecodeError):
            response["body"] = json.loads(raw.content)
        return response
    return process
```

Why these choices:
- `params=event["query"]`: httpx encodes list values as repeated params (`?ids=1&ids=2`)
  and keeps comma values as they are (`?ids=1%2C2`), so both list styles reach the app.
- Return `raw.headers` (httpx `Headers`), **not** `dict(raw.headers)`. `dict(...)`
  lowercases the keys and breaks `response["headers"]["Content-Type"]`. The
  case-insensitive `Headers` object supports both bracket and `.get()` access in any casing.
- `raise_server_exceptions=False`: a 500 comes back as a response, as it would from
  Lambda, instead of being raised.

## Assertion changes (only these)

- `assert response["headers"] == HEADERS` (an exact dict) can't hold: `TestClient` adds
  content-type and length. Relax it to a subset check:
  `assert all(response["headers"].get(k) == v for k, v in HEADERS.items())`.
- Zip-download tests that assert `response["isBase64Encoded"] is True`: the Mangum ↔ API
  Gateway layer produces that field, not `TestClient`. Assert the returned bytes instead,
  e.g. the mocked S3 payload, and keep the `Content-Type: application/zip` check.
- Everything else (status codes, `body["reason"]`, `body["data"]`, `total`) stays unchanged.

## Environment-independent tests

If your auth library checks something environment-specific in the token, for example that
the issuer's region matches the deploy region, tests pass in one environment and fail in
another. Disable that check for tests in an autouse fixture. Don't paper over it by
exporting a matching value: that passes on one branch and fails on the next.

## Validate the session-deadlock fix in isolation

The whole suite hangs for minutes if the fix is wrong. Before you run it, prove that cleanup
runs in the handler's thread with a ~15-line script:
1. A FastAPI app with one `@close_session`-wrapped sync route that records
   `threading.get_ident()` in the handler and in the cleanup.
2. Hit it with `TestClient`.
3. Assert that the two ids are equal and that injected deps, path and query still arrive.

Without `functools.wraps`, FastAPI would see `wrapper(*args, **kwargs)` and inject nothing.

## Diagnosing a hang

`-q` buffers output, so a hang looks like silence. Run one DB-backed test file with
`-o faulthandler_timeout=25`, and pytest prints an all-threads traceback after 25 s. The
deadlock shows the main thread parked in `drop_all` → `do_execute` in the fixture
teardown, which points straight at an unreleased session transaction.
