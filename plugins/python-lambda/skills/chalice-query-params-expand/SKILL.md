---
name: chalice-query-params-expand
description: >-
  Make list-valued query params in a Chalice API (or another AWS Lambda router) accept both
  repeated keys (?ids=1&ids=2) and comma-separated values (?ids=1,2), with one middleware
  and no handler changes. Use when a Chalice API silently keeps only the last value of a
  repeated param, a list or filter endpoint returns one item instead of many,
  `app.current_request.query_params` fed to pydantic drops values, or a router reads
  `queryStringParameters` instead of `multiValueQueryStringParameters`. Also covers direct
  Lambda-to-Lambda invokes: `TypeError: argument of type 'int' is not iterable` on
  non-string values, and filter keys dropped when the two query maps are replaced instead
  of merged. Triggers on: Chalice query params, lambdarest query params, MultiDict
  last-value-wins, "only returns the last id", multi-value query string on Lambda, every
  tenant returns the same count.
---

# Chalice: expand repeated and comma-separated query params

## The bug

`app.current_request.query_params` is a `MultiDict`. Read like a dict (`q["ids"]`,
`dict(q)`, `Model.model_validate(q)`), it returns only the last value of a repeated key.
`?ids=1&ids=2&ids=3` becomes `{"ids": "3"}`, and a list endpoint returns one item. Nothing
fails: HTTP 200, wrong data. The other values are still in `q.getlist("ids")`, but the
usual handler never reads them:

```python
params = app.current_request.query_params or {}
flt = ItemFilter.model_validate(params)      # sees the last value only
```

## The fix: one middleware

Rewrite `request.query_params` into a plain dict before the handlers run. Chalice passes
the `Request` object to HTTP middleware, and `query_params` is a writable attribute.
Handlers and models stay as they are.

The rule:

- collect every value of a key with `getlist`, split strings on commas, flatten;
- one resulting value stays a scalar, several become a list.

Keeping a single value scalar is what makes the middleware safe for every param. `limit`
still arrives as `"50"`, not `["50"]`, and only real lists reach list-typed fields.

```python
# src/chalicelib/middleware.py
from typing import Any


class ExpandQueryParams:
    """?ids=1&ids=2 and ?ids=1,2 both become {"ids": ["1", "2"]}. One value stays scalar."""

    def __call__(self, event, get_response):
        params = getattr(event, "query_params", None)
        if params:
            event.query_params = self.expand(params)
        return get_response(event)

    @staticmethod
    def expand(params) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in params.keys():
            values = []
            for value in params.getlist(key):
                # Split only strings: a direct Lambda invoke can carry ints and bools.
                if isinstance(value, str) and "," in value:
                    values.extend(value.split(","))
                else:
                    values.append(value)
            out[key] = values[0] if len(values) == 1 else values
        return out
```

```python
# src/app.py
from chalicelib.middleware import ExpandQueryParams

app.register_middleware(ExpandQueryParams(), "http")
```

Register it before any other HTTP middleware. Chalice runs middleware in registration
order, so everything registered later, and the handler, sees the plain dict.

## Direct Lambda invokes are not API Gateway events

Through API Gateway every query value is a string. When another service invokes the Lambda
directly with a hand-built event, the values are native JSON types:
`{"multiValueQueryStringParameters": {"id": [7], "notify": [true]}}`.

`"," in 7` raises `TypeError: argument of type 'int' is not iterable` (the wording differs
between Python versions), and the call returns 500. A guard like
`value is not None and "," in value` passes every API Gateway test and fails here. That is
why the middleware checks `isinstance(value, str)`.

Chalice builds `query_params` from `multiValueQueryStringParameters` only. A hand-built
event that puts a param only into `queryStringParameters` reaches the handler without it,
and an event with no `multiValueQueryStringParameters` key at all fails with `KeyError`.
If you own the caller, send every param in the multi-value map.

## Check the models

A list-typed field now gets a list for several values and a scalar for one. Its validator
has to accept both:

```python
@field_validator("ids", mode="before")
@classmethod
def to_int_list(cls, value):
    if isinstance(value, str):            # one value, or a legacy "1,2,3"
        return [int(v) for v in value.split(",")]
    if isinstance(value, int):            # direct invoke
        return [value]
    return value                          # already a list
```

Without the scalar branch, a request with a single id fails validation.

## Tests

Add them with the fix. The API Gateway side of this bug raises nothing, so only a test
that asserts on the returned items keeps it fixed. Don't assert on "no exception".

Go through the real request path, not only `expand()` in isolation. A test of the helper
alone misses a middleware that was never registered.

```python
import json

import pytest
from chalice.app import Request
from chalice.test import Client

from app import app
from chalicelib.middleware import ExpandQueryParams


@pytest.mark.parametrize("url", [
    "/items?ids=1&ids=2&ids=3",     # repeated: the bug, used to return item 3 only
    "/items?ids=1,2,3",             # comma
    "/items?ids=1,2&ids=3",         # mixed
])
def test_both_list_forms_return_every_item(url):
    with Client(app) as client:
        body = json.loads(client.http.get(url).body)
    assert [item["id"] for item in body["data"]] == [1, 2, 3]


@pytest.mark.parametrize("multi, expected", [
    ({"limit": ["50"]}, {"limit": "50"}),                              # one value stays scalar
    ({"kind": ["a", "b"], "limit": ["50"]}, {"kind": ["a", "b"], "limit": "50"}),
    ({"id": [7]}, {"id": 7}),                                          # direct invoke: int
    ({"notify": [True]}, {"notify": True}),                            # direct invoke: bool
    ({"ids": [7, 8]}, {"ids": [7, 8]}),
])
def test_scalars_and_native_types_survive(multi, expected):
    request = Request({
        "multiValueQueryStringParameters": multi,
        "headers": {}, "pathParameters": None, "stageVariables": None, "body": None,
        "requestContext": {"httpMethod": "GET", "resourcePath": "/items"},
    })
    ExpandQueryParams()(request, lambda event: None)
    assert request.query_params == expected
```

The second test is not optional: the int and bool cases are the ones that turn into 500s
and never show up through API Gateway. If you changed a list validator to accept a scalar,
also send that field exactly once through the client.

Keep these tests free of the database and of credentials, so they still run when the rest
of the suite is blocked by something unrelated.

## Other Lambda routers (lambdarest and similar)

Any router that reads `queryStringParameters` has the same bug: API Gateway keeps only the
last value of a repeated key there. lambdarest builds `event["json"]["query"]` from that
map and never looks at `multiValueQueryStringParameters`.

There is no middleware hook, so normalize the event once, before the router sees it:

```python
def expand_query(event):
    merged = dict(event.get("queryStringParameters") or {})      # base: single-value map
    for key, values in (event.get("multiValueQueryStringParameters") or {}).items():
        if not isinstance(values, list):                         # hand-built events
            values = [values]
        flat = []
        for value in values:
            if isinstance(value, str) and "," in value:
                flat.extend(value.split(","))
            else:
                flat.append(value)
        merged[key] = flat[0] if len(flat) == 1 else flat
    event["queryStringParameters"] = merged or None
    return event


def lambda_handler(event, context):
    return router(expand_query(event), context)
```

Merge the two maps, don't replace one with the other. API Gateway fills both with the same
keys, but a direct invoke may put `tenant_id` only into `queryStringParameters` and
`kind` only into `multiValueQueryStringParameters`. Code that takes the multi-value map
when it is present drops `tenant_id`, and every tenant gets the same unfiltered result.
Add that case to the tests: `{"tenant_id": "5"}` plus `{"kind": ["a"]}` must give
`{"tenant_id": "5", "kind": "a"}`.

Then delete any per-handler loops over `multiValueQueryStringParameters`. One central fix
replaces them.

With lambdarest, leave out params that a handler's JSON schema declares as `type: array`:
lambdarest splits those comma strings itself and fails on a value that is already a list.

## Gotchas

- Don't lowercase or otherwise rewrite the values. Ids and tokens can be case-sensitive.
- Replacing the `MultiDict` with a dict breaks code that calls `.getlist()` on
  `query_params` later. Grep for `getlist` before you register the middleware.
- An empty query string leaves `query_params` as `None`, as before. Handlers keep their
  `or {}`.
