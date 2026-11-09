---
name: fastapi-pydantic-patterns
description: Conventions for FastAPI + pydantic v2 services - query-parameter models with a `.make()` factory, list params that accept both `?id=1&id=2` and `?id=1,2`, reusable Annotated types, response envelopes, validators that return clean 4xx errors, settings, and ORM-to-response conversion. Use when adding or reviewing endpoints, request/response models, validators or custom types in a FastAPI app, even if the user only says "add an endpoint" or "add a filter".
---

# FastAPI + pydantic v2 patterns

These conventions keep endpoints small and predictable: parsing and validation live in
models, the endpoint only wires dependencies, calls the CRUD layer and wraps the result.
Follow them unless the project already has a different, consistent convention. In that
case follow the project and say so.

## 1. Where each parameter goes

| Parameter | Where |
|---|---|
| Path parameter | Endpoint signature: `order_id: int` |
| One or two simple query params | Endpoint signature: `limit: Annotated[int, Query(ge=1, le=500)] = 100` |
| Several query params, lists, or cross-field rules | A query model (section 2) |
| Request body | A pydantic model in the signature (section 5) |

Don't add list parsing or validators to fields that don't need them.

## 2. Query model with a `.make()` factory

Plain type hints on the model, FastAPI `Query()` metadata in a static factory. Validators
then run on a normal `BaseModel`, and FastAPI still documents every parameter in OpenAPI.

```python
from datetime import datetime
from typing import Annotated, Optional

from fastapi import Query
from pydantic import BaseModel, NonNegativeInt, field_validator, model_validator

from core.validators import check_date_range, split_csv


class OrderQuery(BaseModel):
    warehouse_id: Optional[list[int]] = None
    status: Optional[list[str]] = None
    created_from: Optional[datetime] = None
    created_till: Optional[datetime] = None
    limit: int = 1000
    offset: int = 0

    _split = field_validator("warehouse_id", "status", mode="before")(split_csv)
    _dates = model_validator(mode="after")(check_date_range("created_from", "created_till"))

    @staticmethod
    def make(
        warehouse_id: Annotated[Optional[list[str]], Query(alias="warehouse_ids", description="Filter by warehouse")] = None,
        status: Annotated[Optional[list[str]], Query()] = None,
        created_from: Annotated[Optional[datetime], Query()] = None,
        created_till: Annotated[Optional[datetime], Query()] = None,
        limit: Annotated[NonNegativeInt, Query(le=10_000)] = 1000,
        offset: Annotated[NonNegativeInt, Query()] = 0,
    ) -> "OrderQuery":
        return OrderQuery(
            warehouse_id=warehouse_id, status=status,
            created_from=created_from, created_till=created_till,
            limit=limit, offset=offset,
        )
```

Name the dependency `args` in every endpoint, so handlers read the same way.

`.make()` lets you use aliases (`warehouse_ids` in the URL, `warehouse_id` in code, or
both singular and plural names) and keep per-parameter OpenAPI metadata next to
model-level validators. Test both `?x=1,2` and `?x=1&x=2`.

### List parameters: accept both spellings

Clients send lists as `?status=new&status=paid` or `?status=new,paid`. Accept both with
one `mode="before"` validator, so neither form silently loses values:

```python
# core/validators.py
def split_csv(value):
    """['1,2', '3'] or '1,2,3' -> ['1', '2', '3']; leaves None and non-strings alone."""
    if value is None:
        return value
    if isinstance(value, (str, int)):
        value = [value]
    out: list[str] = []
    for item in value:
        out += [part.strip() for part in str(item).split(",") if part.strip()]
    return out
```

Then let pydantic coerce the strings to `int` etc. as usual.

## 3. Endpoint

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.auth import Credentials, get_credentials
from core.db import get_db
from core.logger import logger

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=OrderListResponse)
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    args: Annotated[OrderQuery, Depends(OrderQuery.make)],
    credentials: Annotated[Credentials, Depends(get_credentials)],
):
    """Shown in OpenAPI."""
    logger.info(args.model_dump_json())
    args.warehouse_id = restrict_to_allowed(args.warehouse_id, credentials)
    rows, total = crud.list_orders(db, args)
    return OrderListResponse(data=rows, total=total)
```

- Use `Annotated[..., Depends(...)]` for every dependency.
- Authorization filtering happens before the query, not after it.
- No business logic in the endpoint beyond that.

## 4. Reusable Annotated types (`core/datatypes.py`)

```python
from datetime import datetime, time, timezone
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field, PlainSerializer


def _to_utc(x: datetime) -> datetime:
    return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x.astimezone(timezone.utc)

# input
DatetimeUTC = Annotated[datetime, AfterValidator(_to_utc)]

# output
DatetimeOutUTC = Annotated[datetime, AfterValidator(_to_utc), PlainSerializer(lambda x: x.isoformat())]

# validation
Sku = Annotated[str, Field(pattern=r"^[A-Z0-9]{4,12}$")]
Ratio = Annotated[float, Field(ge=0, le=1)]

# transformation
Rounded3 = Annotated[float, AfterValidator(lambda x: round(x, 3))]
ClampedRatio = Annotated[float, AfterValidator(lambda x: round(max(0.0, min(1.0, x)), 3))]
WholeHour = Annotated[time, AfterValidator(lambda x: x.replace(minute=0, second=0, microsecond=0))]
TruncatedInt = Annotated[int, BeforeValidator(lambda x: int(float(x)))]
```

```python
class StockLevel(BaseModel):
    sku: Sku
    updated_at: Optional[DatetimeOutUTC] = None
    fill_ratio: ClampedRatio
```

## 5. Request and response models

```python
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class OrderUpdate(BaseModel):
    note: Optional[str] = None
    status: Optional[str] = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: Optional[DatetimeOutUTC] = None


class Envelope(BaseModel):
    reason: str = "ok"
    message: Optional[str] = None
    data: Optional[Any] = None


class OrderListResponse(Envelope):
    total: int
    data: list[OrderOut]
```

In pydantic v2 an `Optional[X]` field without a default is **required**. Every optional
field needs an explicit `= None`. See the `pydantic-v2-migration` skill.

## 6. Validators that return a clean 4xx

Raise a project exception with a status code from validators instead of a bare
`ValueError`, so the exception handler returns the same envelope as every other error.

```python
# core/exceptions.py
from typing import Any

from starlette import status


class RequestValidationFailed(Exception):
    def __init__(self, message: str, *, reason: str = "invalid_field",
                 data: Any = None, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message, self.reason, self.data, self.status_code = message, reason, data, status_code
```

```python
# core/validators.py
def check_date_range(start: str, end: str):
    """Model-level 'after' validator factory: end must not be before start."""
    def validator(model):
        a, b = getattr(model, start), getattr(model, end)
        if a and b and b < a:
            raise RequestValidationFailed(f"{end} < {start}", status_code=422)
        return model
    return validator
```

In pydantic v2 an `after` model validator receives the **model instance** and must return
it. Don't use the v1-style `(cls, values)` signature.

For a JSON string stored in a column, parse it in a `mode="before"` field validator:

```python
class ShipmentOut(BaseModel):
    items: list[ItemOut]

    @field_validator("items", mode="before")
    @classmethod
    def parse_json(cls, v):
        return json.loads(v) if isinstance(v, str) else v
```

## 7. Settings

```python
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_dsn: Optional[str] = None
    database_host: Optional[str] = None
    database_user: Optional[str] = None
    database_password: Optional[str] = None
    database_name: Optional[str] = None
    database_port: int = 5432
    log_level: str = "INFO"

    @model_validator(mode="after")
    def build_dsn(self):
        if self.database_dsn is None:
            self.database_dsn = (
                f"postgresql://{self.database_user}:{self.database_password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        return self


settings = Settings()  # once, at module level
```

Fill missing parts from your secret store, for example a parameter store, inside the
validator when the environment variables are absent.

## 8. Enums and mixins

```python
class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"

sort: Annotated[SortDirection, Query()] = SortDirection.asc
```

Compose response models from small mixins instead of copying fields:

```python
class WithWarehouse(BaseModel):
    warehouse: WarehouseRef

class WithCapacity(BaseModel):
    capacity: Optional[int] = None

class ZoneOut(ZoneBase, WithWarehouse, WithCapacity):
    pass
```

## 9. ORM row → response model

Keep the database shape and the API shape separate. Load the row into an ORM-shaped model,
then convert it explicitly:

```python
class OrderRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    payload: dict

    @field_validator("payload", mode="before")
    @classmethod
    def parse_json(cls, v):
        return json.loads(v) if isinstance(v, str) else v

    def to_out(self) -> OrderOut:
        return OrderOut(id=self.id, status=self.status, **self.payload)


def list_orders(db: Session, args: OrderQuery) -> list[OrderOut]:
    return [OrderRow.model_validate(r).to_out() for r in query(db, args).all()]
```

## Checklist for a new endpoint

- Parameters placed per section 1. Lists accept both spellings.
- Every `Optional` field has `= None`.
- Validators raise the project exception with a 4xx, not `HTTPException` and not a bare `ValueError`.
- `response_model` is set, and the response uses the envelope.
- Authorization filtering happens before the query.
- There is a test for each new validator and for both list spellings.
