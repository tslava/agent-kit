# FastAPI translation templates

Concrete code for each layer. The examples use a fictional `inventory-api` (orders,
warehouses) with a `{data, total, message, reason}` envelope. Preserve *your* envelope,
CORS headers, status codes and URLs exactly.

## app.py

```python
import sentry_sdk
from fastapi import FastAPI
from mangum import Mangum
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from routers.orders import orders_api           # ... other routers
from responses import register_exception_handlers
from settings import environment

sentry_sdk.init(
    dsn=environment.sentry_dsn,
    max_breadcrumbs=50,
    auto_enabling_integrations=False,   # keep OFF: see SKILL.md "Sentry auto-enabling"
    integrations=[StarletteIntegration(), FastApiIntegration(), SqlalchemyIntegration()],
)

# Rich metadata + /docs under one public subtree = a swagger.yaml-grade spec.
# A bare FastAPI(title=...) gives a thin spec: no metadata, no servers, mangled ids.
app = FastAPI(
    title="Inventory API",
    version="1.0.0",
    description="Orders and warehouses.",
    contact={"name": "API team", "email": "api-team@example.com"},  # harmless email-validator warning
    servers=[
        {"url": "https://dev.api.example.com/inventory", "description": "Development"},
        {"url": "https://api.example.com/inventory", "description": "Production"},
    ],
    # Nest docs under /docs/* so one public API Gateway subtree exposes them.
    openapi_url="/docs/openapi.json",
    docs_url="/docs/openapi",
    redoc_url="/docs/redoc",
    # Sections in the UI. Without tags every operation lands under "default".
    openapi_tags=[
        {"name": "orders", "description": "Orders"},
        # ... one entry per group
    ],
    # Clean operationIds (the route function name) instead of the mangled default.
    generate_unique_id_function=lambda route: route.name,
)
register_exception_handlers(app)
app.include_router(orders_api, tags=["orders"])   # ... include the rest
# A single-file app (no Blueprints -> no APIRouter) passes tags=[...] and summary=...
# on each @app.get(...) decorator instead.


# Validation errors are returned as 400 (see register_exception_handlers), but FastAPI
# auto-adds a 422 to every validated operation. Strip it so the spec matches the
# real contract (200 + 400/401/404).
_default_openapi = app.openapi


def _custom_openapi():
    schema = _default_openapi()
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)
    return schema


app.openapi = _custom_openapi

# Lambda entrypoint. lifespan="off": no ASGI startup/shutdown on Lambda.
handler = Mangum(app, lifespan="off")
```

Do **not** add an `@app.middleware("http")` session-cleanup coroutine. It runs in the
event-loop thread and clears the wrong thread's scoped session (see the deadlock section).

## Session cleanup decorator

```python
import functools

def close_session(session):
    def decorator(function):
        @functools.wraps(function)   # preserve the signature so FastAPI still injects params
        def wrapper(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            finally:
                session.remove()     # same worker thread as the handler -> lock released
        return wrapper
    return decorator
```

## dependencies.py (new)

```python
import json
from typing import Any, Optional

from fastapi import Header, Request

from auth_lib import Credentials, decode_token   # your shared auth library


def current_credentials(
    authorization: Optional[str] = Header(default=None),
) -> Credentials:
    # Replaces the Chalice-side "current credentials" property.
    # Use the same header name your clients already send.
    return decode_token(authorization)


async def raw_json_body(request: Request) -> Any:
    # Replaces app.current_request.json_body. The body may be a dict OR a list (batch endpoints).
    body = await request.body()
    if not body:
        return None
    return json.loads(body)
```

## responses.py (envelope + exception handlers)

```python
import sentry_sdk
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError

CORS_HEADERS = {
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,"
                                    "X-Amz-Security-Token,X-Amz-User-Agent",
    "Access-Control-Allow-Methods": "OPTIONS,GET,PUT,PATCH,POST,DELETE",
    "Access-Control-Allow-Origin": "*",
}


def _json_response(body: "Envelope", status_code: int, headers=None) -> Response:
    return Response(
        content=body.model_dump_json(),          # byte-identical to the old envelope
        status_code=status_code,
        media_type="application/json",
        headers={**(headers or {}), **CORS_HEADERS},
    )
# respond_ok / respond_not_found / respond_forbidden / respond_internal_error /
# respond_validation_error / respond_invalid_field all delegate to _json_response.


def file_response(content: bytes, file_name: str, extension: str = "zip") -> Response:
    return Response(
        content=content, status_code=200, media_type=f"application/{extension}",
        headers={"Content-Disposition": f'attachment; filename="{file_name}.{extension}"',
                 **CORS_HEADERS},
    )


class NotFoundError(Exception): ...
class NotOwnerError(Exception): ...


def register_exception_handlers(app) -> None:
    @app.exception_handler(ValidationError)
    async def _pydantic(_request, exc):
        return respond_validation_error(exc.errors())

    @app.exception_handler(RequestValidationError)
    async def _request(_request, exc):
        # Typed params/bodies make FastAPI prefix each error loc with its source
        # ("body"/"query"/"path"). Strip it so loc keeps the pre-typing shape,
        # e.g. ["sku"], not ["body", "sku"].
        errors = []
        for err in exc.errors():
            err = dict(err)
            loc = err.get("loc") or ()
            if loc and loc[0] in ("body", "query", "path"):
                err["loc"] = loc[1:]
            errors.append(err)
        return respond_validation_error(errors)

    @app.exception_handler(Unauthorized)
    async def _unauthorized(_request, exc):
        return respond_forbidden("Unauthorized", 401)

    @app.exception_handler(PermissionError)
    async def _forbidden(_request, exc):
        return respond_forbidden("Forbidden", 403)

    @app.exception_handler(NotFoundError)
    async def _not_found(_request, exc):
        return respond_not_found("Not Found")

    @app.exception_handler(NotOwnerError)
    async def _not_owner(_request, exc):
        return respond_invalid_field("Operation not permitted.")

    @app.exception_handler(Exception)
    async def _unhandled(_request, exc):
        sentry_sdk.capture_exception(exc)
        return respond_internal_error()
```

`respond_validation_error` must sanitize pydantic v2 `errors()` before serializing: their
`ctx` can hold non-JSON `Exception` objects.

## Typed query params, bodies and responses

**Port to typed signatures, not the raw `Request`.** A faithful port *can* read everything
from `request.query_params` / `raw_json_body`, and it will pass every test. But FastAPI then
sees no parameters, no request body and no response schema, and `/docs` is threadbare. Typed
signatures cost a little more code and produce a spec as detailed as a hand-written
`swagger.yaml`. Runtime behavior stays identical, and the tests remain the oracle.

### Query params → a filter `BaseModel` with a `.make()` factory

`?ids=1,2` arrives as the single element `["1,2"]`. Without a `before` validator that
splits it, `list[int]` rejects it. The `.make()` staticmethod keeps that under your control:
- its params are typed `list[str]`, so nothing is coerced before the split;
- it can expose both singular and plural names and per-parameter OpenAPI metadata;
- it feeds a normal model constructor, so model validators run as usual.

The model also stays usable via `model_validate` in tests. Test both list forms.

```python
from typing import Annotated, Optional

from fastapi import Query
from pydantic import BaseModel, field_validator


def split_csv(value):
    if isinstance(value, (str, int)):
        value = [value]                     # a value arriving via an alias isn't wrapped in a list
    if isinstance(value, list):
        out = []
        for v in value:
            out += str(v).split(",")        # handles both ?ids=1,2 and ?ids=1&ids=2
        return out
    return value


def _pick(*vals):                           # first non-None of the singular/plural aliases
    return next((v for v in vals if v is not None), None)


class OrderFilter(BaseModel):
    id: Optional[list[int]] = None
    owner_id: Optional[int] = None
    warehouse_id: Optional[list[int]] = None
    offset: int = 0
    limit: int = 50

    _split = field_validator("id", "warehouse_id", mode="before")(split_csv)

    @staticmethod
    def make(
        # expose BOTH singular and plural names; each is documented once, here
        ids: Annotated[Optional[list[str]], Query(description="Filter by id")] = None,
        id: Annotated[Optional[list[str]], Query(description="Alias of ids")] = None,
        owner_id: Annotated[Optional[int], Query(description="Admin-only cross-owner filter")] = None,
        warehouse_id: Annotated[Optional[list[str]], Query()] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=50)] = 50,
    ) -> "OrderFilter":
        return OrderFilter(
            id=_pick(ids, id), owner_id=owner_id,
            warehouse_id=warehouse_id, offset=offset, limit=limit,
        )
```

### Generic response envelope: documents the schema while the handler returns a raw `Response`

Keep returning the byte-identical `Response` from `respond_ok(...)`. Do NOT switch
handlers to `return model`: that re-serializes and can change the bytes. FastAPI **skips**
`response_model` serialization when a handler returns a `Response`, but it still emits the
schema into the spec. A generic envelope as `response_model` is pure documentation with
zero runtime risk:

```python
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):   # mirror the runtime envelope EXACTLY:
    reason: str = "ok"                      # drop fields your service doesn't send,
    data: Optional[T] = None                # and use data: list[T] for list routes.
    message: Optional[str] = None
    total: Optional[int] = None
```

FastAPI can't infer the error responses, so document them with a shared dict once per
router. The handlers return **400** for validation, so document 400/401/404. The 422 that
FastAPI still auto-adds is stripped in `app.openapi()` (see app.py):

```python
COMMON_ERROR_RESPONSES = {
    400: {"description": "Bad input parameter"},
    401: {"description": "Unauthorized"},
    404: {"description": "Requested resource not found"},
}
# APIRouter(responses=COMMON_ERROR_RESPONSES), or responses=... per route
```

### owner_id: Optional in Create/Update, set after validation

In a multi-tenant API, users usually OMIT `owner_id` on create/update: it is forced to their
own tenant. A typed body with a **required** `owner_id` then returns 422 for every user
request. Make it `Optional[int] = None` in the Create/Update models, and set the real value
after validation with `set_owner`.

## utils.py: request helpers on typed models, not on the raw request

```python
def require_permission(credentials: Credentials, operation: str) -> tuple[str, int]:
    if credentials.role == "user":
        if not credentials.can(operation):
            raise PermissionError(f"You do not have permission to {operation}")
    elif credentials.role != "admin":
        raise Unauthorized
    return credentials.role, credentials.tenant_id


def scope_to_owner(credentials, args) -> None:
    # GET filters: a user may only pass their own owner_id; force it either way.
    if credentials.role == "user":
        if args.owner_id is not None and str(args.owner_id) != str(credentials.tenant_id):
            raise PermissionError("You do not have permission to filter by this owner_id")
        args.owner_id = credentials.tenant_id


def set_owner(credentials, model) -> None:
    # POST/PUT bodies: overwrite owner_id for the user role (not every model has it).
    if credentials.role == "user" and hasattr(model, "owner_id"):
        model.owner_id = credentials.tenant_id
```

## Router pattern (Blueprint → APIRouter)

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from auth_lib import Credentials
from dependencies import current_credentials
from settings import close_session, session

orders_api = APIRouter(responses=COMMON_ERROR_RESPONSES)   # 400/401/404 on every route


@orders_api.get("/orders", response_model=models.ApiResponse[list[models.Order]])
@close_session(session)                        # INNER decorator, closest to def
def list_orders(
    args: Annotated[models.OrderFilter, Depends(models.OrderFilter.make)],
    credentials: Annotated[Credentials, Depends(current_credentials)],
):
    utils.require_permission(credentials, "read")
    utils.scope_to_owner(credentials, args)
    rows, total = db.list_orders(session, args)
    return respond_ok(data=[models.Order.model_validate(r) for r in rows], total=total)


@orders_api.post("/orders", response_model=models.ApiResponse[models.Order])
@close_session(session)
def create_order(
    order: models.OrderCreate,                 # typed body -> requestBody schema in the spec
    credentials: Annotated[Credentials, Depends(current_credentials)],
):
    utils.require_permission(credentials, "create")
    utils.set_owner(credentials, order)        # the user role can't spoof owner_id
    ...


@orders_api.put("/orders/{order_id}", response_model=models.ApiResponse[models.Order])
@close_session(session)
def update_order(
    order_id: str,                             # accept str, keep the existing validator
    update: models.OrderUpdate,
    credentials: Annotated[Credentials, Depends(current_credentials)],
):
    order_id = models.OrderIdValidator.validate(order_id)   # -> 400 on a bad id
    utils.set_owner(credentials, update)
    ...
```

Notes:
- Keep the module-level router variable named like the old blueprint, so `app.py` imports
  don't churn.
- Accept path params as `str` and reuse the existing id validator, so a bad id raises a
  pydantic `ValidationError` and returns the same 400 envelope. Typing the param as `int`
  gives FastAPI's own 422 instead and changes the contract.
- `@close_session(session)` stays the inner decorator, closest to `def` (see the deadlock
  section in SKILL.md).
- An endpoint that accepts one or many bodies (a single object OR a batch list) unions
  the models, `body: ItemCreate | ItemBatchCreate`, and branches on `isinstance`. The spec
  documents both shapes.
