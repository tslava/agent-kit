---
name: pydantic-v2-migration
description: >-
  Migrate pydantic v1 code to v2: models, validators, settings and serialization. Covers
  what the mechanical renames miss: Optional fields that become required, validators that
  change when they run, stricter type coercion, a different JSON output and error shape,
  and v1 methods that keep working behind deprecation warnings. Use when upgrading pydantic
  1.x to 2.x, or when an upgraded service shows `Field required`, `BaseSettings has been
  moved to the pydantic-settings package`, `Input should be a valid string`, `Extra inputs
  are not permitted`, or 500s where it used to return 200 or 400. Triggers on: pydantic v1
  to v2, pydantic 2 migration, @validator to @field_validator, root_validator, .dict() to
  model_dump, orm_mode, json_encoders.
---

# pydantic v1 → v2

The renames are the easy part, and the official migration guide lists them all. This skill
gives an order of work and the changes that pass review and then break at runtime.

## Order of work

1. Renames (next section).
2. Optional fields: add `= None`.
3. Validators: check when each one runs.
4. Settings.
5. Behavior changes: coercion, JSON output, error shape.
6. Run the tests with deprecation warnings as errors.

Run the tests after each step.

## 1. Renames

| v1 | v2 |
|---|---|
| `Model.parse_obj(x)` | `Model.model_validate(x)` |
| `Model.parse_raw(s)` | `Model.model_validate_json(s)` |
| `Model.from_orm(obj)` | `Model.model_validate(obj)`, with `from_attributes=True` |
| `m.dict()` | `m.model_dump()` |
| `m.json()` | `m.model_dump_json()` |
| `m.copy(update=...)` | `m.model_copy(update=...)` |
| `Model.construct()` | `Model.model_construct()` |
| `Model.update_forward_refs()` | `Model.model_rebuild()` |
| `Model.__fields__` | `Model.model_fields` |
| `class Config:` | `model_config = ConfigDict(...)` |
| `orm_mode = True` | `from_attributes=True` |
| `Field(regex=...)` | `Field(pattern=...)` |
| `BaseSettings` from `pydantic` | `BaseSettings` from `pydantic_settings`, a separate package |
| `GenericModel` | `BaseModel` with `Generic[T]` |
| `__root__` | `RootModel` |

The `bump-pydantic` tool applies part of this list. Treat its diff as a draft and read it.

**Most v1 names still work.** `.dict()`, `.json()`, `parse_obj` and `@validator` are kept as
shims that emit `PydanticDeprecatedSince20`. A half-migrated codebase passes its tests, so
a green suite doesn't mean the renames are done. Step 6 closes that gap.

## 2. Optional fields become required

In v1, `name: Optional[str]` had an implicit default of `None`. In v2 the field is required
and merely allowed to be `None`:

```python
class Order(BaseModel):
    note: Optional[str]          # v2: Order() -> "Field required [type=missing]"
    note: Optional[str] = None   # what v1 meant
```

The syntax is valid in both versions, nothing warns, and the error appears only when the
field is absent. Find the fields:

```bash
grep -rnE "^\s+\w+: Optional\[[^=]*$" src tests
```

Where it hides:

- **Response models.** Tests that build the model with every field pass. The handler that
  omits `message` raises, and a 200 becomes a 500.
- **The error path.** If the 400 handler builds the same response model, a validation
  error turns into a 500 instead of a 400.
- **Settings.** A missing default fails only when the environment variable is absent.
  Test fixtures usually set it. Instantiate the settings class once with the variable unset.

## 3. Validators

**`@validator` → `@field_validator`, with `@classmethod` under it.**

Keep the moment the validator runs. A v1 `@validator("x")` ran after type coercion, and so
does `@field_validator("x")`. Only `pre=True` becomes `mode="before"`. A "before" validator
gets the raw input:

```python
@field_validator("created_at", mode="before")     # wrong: v1 had no pre=True
@classmethod
def to_utc(cls, v):
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
# JSON input -> AttributeError: 'str' object has no attribute 'tzinfo'
```

That `AttributeError` is not a validation error. It escapes as a raw exception and the
request ends in a 500.

| v1 | v2 |
|---|---|
| `pre=True` | `mode="before"` |
| `always=True` | `Field(default, validate_default=True)` on the field; without it the validator is skipped when the default is used |
| `each_item=True` | validate the item type: `list[Annotated[int, AfterValidator(check)]]` |
| `values` argument | `info: ValidationInfo`; `info.data` holds the fields validated so far |
| `allow_reuse=True` | gone, not needed |

**`@root_validator` → `@model_validator`.**

- `mode="after"` is an instance method. It takes `self` and returns `self`:

  ```python
  @model_validator(mode="after")
  def check_range(self):
      if self.date_till < self.date_from:
          raise ValueError("date_till < date_from")
      return self
  ```

  The v1-shaped `(cls, values)` signature still runs, with a deprecation warning since
  pydantic 2.12. Don't write it.
- `@root_validator(pre=True)` becomes `@model_validator(mode="before")` plus `@classmethod`.
  It gets the raw input, which is not always a dict.
- A shared check is a plain function that takes the model and returns it:
  `_check = model_validator(mode="after")(check_range)`.

**Which exceptions count.** Only `ValueError` and `AssertionError` raised in a validator
become a `ValidationError`. In v1 a `TypeError` did too. In v2 it propagates as it is.

## 4. Settings

- Add the `pydantic-settings` package and import `BaseSettings` from `pydantic_settings`.
  The old import fails with `PydanticImportError: BaseSettings has been moved to the
  pydantic-settings package`.
- `class Config: env_file = ...` becomes `model_config = SettingsConfigDict(env_file=...)`.
- **A `.env` file may no longer hold unrelated keys.** Every key that matches no field
  raises `Extra inputs are not permitted`. Set `extra="ignore"` in `SettingsConfigDict` if
  the file is shared with other tools. Real environment variables are not affected.
- A field computed from other fields moves to an "after" model validator:

  ```python
  class Settings(BaseSettings):
      database_host: str = "127.0.0.1"
      database_dsn: Optional[str] = None

      @model_validator(mode="after")
      def build_dsn(self):
          if self.database_dsn is None:
              self.database_dsn = f"postgresql://{self.database_host}/app"
          return self
  ```

## 5. Behavior that changed

These need no code change to compile, so nothing points at them.

| What | v1 | v2 |
|---|---|---|
| `str` field gets an `int` | coerced to `"123"` | `Input should be a valid string`. Fix the type, or set `coerce_numbers_to_str=True` in the model config |
| `int` field gets `1.5` | truncated to `1` | `Input should be a valid integer, got a number with a fractional part`. `1.0` and `"5"` still pass |
| JSON output | `{"a": 1, "b": 2}` | `{"a":1,"b":2}`: compact. Tests that compare raw body strings fail; compare parsed JSON |
| UTC datetime in JSON | `2026-01-01T00:00:00+00:00` | `2026-01-01T00:00:00Z` |
| `json_encoders` | per-type lambdas in `Config` | deprecated. Use `Annotated[datetime, PlainSerializer(fn)]` or `@field_serializer` |
| `model_validate(orm_obj)` without `from_attributes=True` | n/a | `Input should be a valid dictionary or instance of Order` |

`ValidationError.errors()` has a new shape:

- `type` and `msg` are renamed: `value_error.missing` / `field required` is now `missing` /
  `Field required`. Clients and tests that match on the old strings need an update.
- Each entry gains `input` and `url`.
- For an error raised in your validator, `ctx` holds the exception object, so
  `json.dumps(e.errors())` raises `TypeError`. Use
  `e.errors(include_url=False, include_context=False)` or `e.json()`.

With FastAPI, pydantic v2 needs FastAPI 0.100 or newer. For query-parameter models see the
`fastapi-pydantic-patterns` skill.

## 6. Verify

```bash
uv run pytest -W error::DeprecationWarning
```

Every v1 shim that is still called now fails its test. If other libraries flood the run
with their own deprecations, narrow the filter to
`-W error::pydantic.warnings.PydanticDeprecationWarning`.

Then grep for leftovers in code the tests don't reach:

```bash
grep -rnE "parse_obj|parse_raw|from_orm|\.dict\(\)|\.json\(\)|@validator|@root_validator" src tests
grep -rnE "class Config|orm_mode|json_encoders|__fields__|update_forward_refs" src tests
```

`.json()` also matches `ValidationError.json()` and HTTP client responses. Those stay.
