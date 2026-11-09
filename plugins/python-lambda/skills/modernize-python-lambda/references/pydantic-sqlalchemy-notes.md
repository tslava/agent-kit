# pydantic v2 + SQLAlchemy 2.0 — stack-specific deltas

Read the `pydantic-v2-migration` and `sqlalchemy-v2-migration` skills for the full rules.
This file records what actually bit on real Chalice Lambdas beyond those skills.

## pydantic v2

- **`@validator` → `@field_validator` + `@classmethod`.** `pre=True` becomes
  `mode="before"`. `always=True` becomes `validate_default=True` on the field; drop it when
  the validator returns `None` unchanged anyway. `each_item=False` was the default, drop it.
- **Cross-field validators → `@model_validator(mode="after")`.** The classic Settings DSN
  builder read other fields via the `values` dict; in v2 use `self`:
  ```python
  from typing import Optional

  from pydantic import model_validator
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      database_host: str = "127.0.0.1"
      database_dsn: Optional[str] = None

      @model_validator(mode="after")
      def make_dsn(self) -> "Settings":
          if not self.database_dsn:
              self.database_dsn = f"postgresql://…{self.database_host}…"
          return self
  ```
- **`parse_obj` → `model_validate`; `.dict()` → `model_dump()`; `.json()` →
  `model_dump_json()`.** The middleware/handler that does
  `Model.parse_obj(query_params)` becomes `Model.model_validate(query_params)`.
- **The Optional-default trap lives in RESPONSE models too.** This is the one that
  silently breaks. A response wrapper like:
  ```python
  class ResponseBody(BaseModel):
      reason: str = "ok"
      data: Optional[Any]        # v1: implicitly None. v2: REQUIRED → ValidationError
      message: Optional[str]     # same
  ```
  passes tests that build it with all fields, but `ResponseBody(data=...)` (no `message`)
  raises `ValidationError`, which a catch-all exception handler turns into a 400/500.
  HTTP 200 tests go red with no traceback pointing at the model. Add `= None` to every
  Optional field, in **every** `BaseModel` and **every `BaseSettings`**. Grep for
  `Optional[` without a default (Step 0 has the command).
- **The same trap hides in Settings.** A `database_dsn: Optional[str]` in `BaseSettings`
  only fails when the environment variable is missing. Test fixtures usually set it, so the
  suite stays green while a cold start without that variable crashes. Instantiate
  `Settings()` once with the variable unset to check.
- **The trap also fires inside your error handler.** If the 400 path builds the same
  response model, a validation error turns into a 500 instead of the expected 400.

## SQLAlchemy 2.0

- **`select([...])` → `select(...)`** (positional, no list).
- **Row unpacking: `Model(**row)` needs `.mappings()`.** In 2.0 a `Row` is tuple-like, so
  `Order(**row)` fails; iterate the mapping view:
  ```python
  for row in connection.execute(query).mappings():
      result.append(Order(**row))
  ```
- **`engine.connect()` no longer autocommits.** This silently breaks write fixtures *and*
  write paths in the app. A test seed that did `with engine.connect() as c: c.execute(insert…)`
  now persists nothing: the transaction is rolled back on close. Use
  `with engine.begin() as c:` (commits on success) or add `c.commit()`.
- **Fix autocommit first, then look again.** Empty tables hide the next failure: with no
  rows, `Model(**row)` never runs. Once the seed commits, the Row-unpacking error
  appears (see "Row unpacking" above).
- **`order.dict()` in an insert → `order.model_dump()`** (this is also the pydantic
  v2 rename; nested models serialize to dicts, fine for JSONB columns; str-enums pass
  through fine for ENUM columns).
- `create_engine(dsn)` needs no `future=True` in 2.0 (it's the default). Core `Table`,
  `Column`, dialect `JSONB`/`ENUM`/`ARRAY` definitions are unchanged.
