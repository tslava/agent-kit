---
name: chalice-to-fastapi
description: >-
  Migrate an AWS Chalice Lambda REST API to FastAPI, served on Lambda via Mangum behind
  the existing API Gateway. Use this whenever the user wants to move a Chalice app to
  FastAPI, replace Chalice, "get off Chalice", or modernize a Chalice Lambda's HTTP
  framework, EVEN IF they name only one piece (e.g. "swap our Chalice blueprints for
  FastAPI routers", "run this Lambda API with FastAPI", "add Mangum"). The migration is
  coupled: once `chalice package` is gone, CDK has to bundle the Lambda, which usually
  also means uv + a newer Python. This skill orders those steps and lists the gotchas that
  actually broke real migrations. Triggers on: chalice to fastapi, replace chalice,
  Blueprint to APIRouter, Mangum on Lambda, chalice package replacement, app.app to
  app.handler, "our chalice API needs to become fastapi".
---

# Chalice → FastAPI migration (Lambda APIs)

## Why this is more than "swap the router"

A Chalice app hides a lot:
- it vendors its own runtime into the deploy package (`chalice package`);
- it owns the Lambda ↔ API Gateway event translation;
- it parses the body and the query string and exposes `app.current_request`;
- it supplies the `IAMAuthorizer` binding.

FastAPI does none of that for Lambda. **Mangum** is the ASGI ↔ Lambda adapter, and *you*
now own request parsing and the response envelope. So the real work is: app shell +
routers + response/exception layer + auth/session dependencies + request parsing + tests
+ `cdk.py` (packaging + handler).

Because `chalice package` is gone, CDK's `PythonFunction` now packages the Lambda: it
bundles the code and pip-installs `src/requirements.txt` in Docker. On a modern repo that
means uv and a current Python, which pulls in the rest of the modernization.

**Surface the true scope to the user up front** and confirm before starting. Confirm the
decisions that genuinely fork the plan, because you cannot infer them:

1. **Deployment shape.** Mangum on the *existing* API Gateway + Lambda (recommended:
   smallest infra change), or a container/Fargate. Default to Mangum.
2. **Test strategy.** Rewrite to `TestClient`. Keep the existing test-facing helpers as a
   shim over `TestClient`, so the test files barely change (`references/testing.md`).
3. **Cutover.** Full in-place replacement on one branch (recommended), or side by side.
4. **Python / packaging.** Usually the latest Python + uv (`modernize-python-lambda`).
5. **Pipeline auth.** Keyless (OIDC) deploys and a DB migration check, if the project has them.

## Sibling skills

This skill orchestrates. Per-domain detail lives in:

| Concern | Skill |
|---|---|
| uv + Python 3.14 + pydantic v2 + SQLAlchemy 2.0 + aws-cdk v2 | `modernize-python-lambda` |
| Release-age cooldown for dependencies | `dependency-cooldown` |
| Query/body parameter patterns (`.make()` factory, comma lists) | `fastapi-pydantic-patterns` |
| pydantic v1 → v2 | `pydantic-v2-migration` |
| The multi-value query-param contract you must keep | `chalice-query-params-expand` |

## Order of operations (each phase independently green)

Order matters: **remove Chalice before bumping Python**. Chalice will never have to import
on the new Python, and each commit stays a clean, testable slice. Run `uv run pytest` after
every phase.

- **Phase A: uv, keep Chalice, keep versions.** Move to uv, split runtime and dev deps, add
  the cooldown, export `src/requirements.txt`. Pin deps to their *current* versions so this
  commit is a pure tooling swap and stays green. Chalice is a **dev** dep here: it vendors
  its own runtime, nothing to bundle yet.
- **Phase B: the FastAPI cutover, on the old Python.** The heart of this skill: "The
  cutover" below, `references/fastapi-translation.md` and `references/testing.md`.
- **Phase C: new Python + CDK packaging.** Chalice is gone, so:
  - bump Python and relax pins to lower bounds;
  - bump `aws-cdk-lib` and the matching `aws-cdk-aws-lambda-python-alpha`;
  - set the new `Runtime.PYTHON_3_x`;
  - convert the Lambdas to **`PythonFunction`**; the API handler is `app.handler`;
  - switch API Gateway to a **catch-all proxy** instead of enumerated routes, plus public `/docs/*`.

  Confirm the CDK constant exists *and* the managed runtime is GA in your regions. If not,
  use the previous version. See `references/packaging-cdk-pipeline.md`.
- **Phase D: pipeline.** The deploy step drops `chalice package` and adds a Docker service,
  `uv export` and `cdk deploy`, because PythonFunction bundles in Docker.
- **Phase E: docs.** README/CLAUDE.md: FastAPI, uv, the Python version, auto-`/docs`.

Commit one concern per phase, in the project's commit convention. **Never commit or push
without explicit approval.** Many pipelines deploy on push.

## The cutover (Phase B)

Preserve exactly:
- URLs, methods and status codes;
- the response envelope (e.g. `{data, total, message, reason}`) and CORS headers;
- authorization at API Gateway and the auth header the clients send;
- binary (zip) downloads.

Code templates for every piece below are in `references/fastapi-translation.md`.

1. **App shell** (`app.py`): `FastAPI(...)`, register routers,
   `handler = Mangum(app, lifespan="off")`. This becomes the CDK `handler="app.handler"`.
2. **Sentry**: `sentry_sdk.init(..., auto_enabling_integrations=False, integrations=[
   StarletteIntegration(), FastApiIntegration(), SqlalchemyIntegration()])`. Turn
   auto-enabling **off**. Otherwise a newer `sentry-sdk` auto-enables *other* installed
   integrations, and its Chalice integration crashes on the tests' `lambda_context=None`.
3. **Response/exception layer**: keep the envelope and CORS. Return a Starlette
   `Response(content=Envelope(...).model_dump_json(), media_type="application/json",
   headers={...CORS})`, so serialization stays byte-identical. Replace a "catch exceptions"
   decorator with `register_exception_handlers(app)`: map validation errors, unauthorized,
   forbidden, not-found and your domain errors, plus a catch-all that reports to Sentry.
4. **Auth + body dependencies**: a `current_credentials(...)` dependency reads the
   token header and replaces the Chalice-side credentials property. Keep an async
   `raw_json_body(request)` (dict/list/None) as a fallback for handlers without a fixed
   body schema. Prefer typed body models (step 5), so the request body is documented.
5. **Typed request/response signatures from the start, so the OpenAPI spec is rich.** A
   port onto the raw `Request` passes every test but produces a THREADBARE `/docs`: no
   params, no request body, no response schema, a single `default` tag. Typed signatures
   keep the runtime behavior and give a spec as detailed as a hand-written `swagger.yaml`.
   - **Query** → a filter `BaseModel` with a `.make()` staticmethod, injected as
     `args: Annotated[Filter, Depends(Filter.make)]`. Type the `.make()` params as
     `list[str]` and split comma lists in a `before` field validator on the model. The
     factory lets you expose singular and plural names (`?id=` and `?ids=`), collapse
     them with `_pick(...)`, and keep per-parameter OpenAPI metadata next to model-level
     validators. Whatever you choose, **test both `?ids=1,2` and `?ids=1&ids=2` on your
     FastAPI version**: list coercion is exactly where a port silently changes the
     contract.
     - **Several filters on one endpoint** (e.g. `ids` AND a `time_from/time_till/limit`
       range): inject several `Depends(make)` side by side instead of one mega-model. Make
       sure their *exposed* query names don't collide. Surface `limit` in only ONE
       `.make()`, or FastAPI emits a duplicate `limit` parameter.
     - **Keep model fields that aren't query params but that `model_dump()` forwards
       downstream.** If a handler forwards `filter.model_dump()` to another Lambda, a
       field like `limit` must stay on the model with its default, even if `.make()`
       doesn't expose it. Dropping it silently changes what is sent downstream.
   - **Body** → a typed `Create`/`Update` model. In multi-tenant APIs where users omit
     `owner_id`, make it `Optional[int] = None` and set the real value after validation
     (`set_owner(credentials, model)`).
   - **Response** → `response_model=ApiResponse[T]`, a generic envelope. Handlers keep
     returning the raw `Response`. FastAPI skips response_model *serialization* for a
     `Response` return, so the bytes stay identical, but it still emits the schema. Pure
     documentation, zero runtime risk.
   - **Errors** → typed params make FastAPI prefix each `loc` with `body`/`query`/`path`.
     Strip that prefix in the `RequestValidationError` handler, so `loc` matches what
     clients and tests expect (`["sku"]`, not `["body", "sku"]`).

   A Chalice middleware that expanded multi-value query params (see
   `chalice-query-params-expand`) is no longer needed: the `.make()` + split validator
   owns the `?ids=1,2` vs `?ids=1&ids=2` contract now. Keep the tests for both forms.
6. **Routers**: each Chalice `Blueprint` → `APIRouter`. `@bp.route("/x", methods=["GET"])`
   → `@router.get("/x")`. Keep the exact paths. Path params become typed function
   arguments. Keep existing id validators, so a bad id stays a 400 and doesn't become
   FastAPI's 422.
7. **Session lifecycle**: see the deadlock section below. Use `@close_session(session)` per
   route, **not** middleware.
8. **Zip download**: return `Response(content=zip_bytes, media_type="application/zip",
   headers={Content-Disposition..., ...CORS})`. Mangum base64-encodes non-text media types.
   API Gateway must list `application/zip` in `binary_media_types`.
9. Delete the Chalice-only middleware, dead blueprint modules, `src/.chalice/` and the
   `chalice` dependency. Add `fastapi` and `mangum` as **runtime** deps: they are bundled now.

## The #1 gotcha: scoped-session cleanup deadlock

**Symptom:** the suite hangs. Not in a test, but in the database fixture teardown at
`Base.metadata.drop_all(...)`, blocked forever on a table lock.

**Cause:** FastAPI runs **sync** path handlers in an anyio worker thread. A sync handler's
query opens a transaction in *that worker thread's* entry of the thread-local
`scoped_session`. An **async middleware** runs cleanup in the event-loop thread and calls
`session.remove()` on the *wrong* thread's registry entry. The worker's transaction stays
open and holds an `ACCESS SHARE` lock, and `DROP TABLE` (which needs `ACCESS EXCLUSIVE`)
blocks indefinitely. Chalice never hit this, because it ran the handler and the cleanup in
one thread.

**Fix:** clean up **per handler, in the handler's thread**, with a decorator that preserves
the signature, so FastAPI dependency injection still works:

```python
import functools

def close_session(session):
    def decorator(fn):
        @functools.wraps(fn)          # exposes fn's real signature via __wrapped__,
        def wrapper(*args, **kwargs):  # so FastAPI still injects path/query/body/deps
            try:
                return fn(*args, **kwargs)
            finally:
                session.remove()       # runs in the SAME worker thread as fn
        return wrapper
    return decorator
```

Apply `@close_session(session)` **below** each `@router.<method>(...)`, so it is the inner
wrapper, closest to `def`. Validate it once with a tiny standalone TestClient script: assert
that the cleanup thread id equals the handler thread id (`references/testing.md`).

## Mangum + direct Lambda invocation (don't over-engineer)

If other services invoke your Lambda **directly**, not through API Gateway, then before building a direct-invoke adapter, check what the caller actually sends. If the
caller builds events with `resource` + `requestContext` + `httpMethod` +
`queryStringParameters`, **Mangum's API Gateway (v1) handler parses them natively**.

Mangum coerces query values to strings, so scalar and int values, comma strings, standard
`multiValueQueryStringParameters` and even list-valued `queryStringParameters` can all
reach your filter validators. Confirm it empirically for your callers
(`references/local-run.md`) rather than assuming either way.

## Gotchas that actually bit

- **Session deadlock**: the big one above. Per-handler `@close_session` + `functools.wraps`.
- **Sentry auto-enabling**: `auto_enabling_integrations=False` + explicit integrations.
  Otherwise the still-installed Chalice integration crashes on `lambda_context=None` in tests.
- **`chalice` is dev; `fastapi` and `mangum` are runtime.** Chalice vendored itself via
  `chalice package`. Once CDK bundles the Lambda, FastAPI, Mangum and Starlette must be in
  `[project.dependencies]` and in the exported `src/requirements.txt`.
- **Package with `PythonFunction`, not a hand-built zip.** `aws_cdk.aws_lambda_python_alpha.
  PythonFunction` bundles and pip-installs in Docker at deploy time. Don't write a build
  script that cross-installs manylinux wheels and zips them: some CI images don't even ship
  `zip`. The alpha package version must match `aws-cdk-lib` exactly, and the deploy step
  needs a Docker service.
- **API Gateway: a catch-all proxy, not enumerated routes.** FastAPI routes internally.
  Calling `add_resource`/`add_method` per path makes CDK emit ~2 `Lambda::Permission` each,
  and that overflows the **20 KB Lambda resource-policy limit**
  (`final policy size … bigger than 20480`). Use
  `api.root.add_proxy(default_method_options=MethodOptions(**auth))`.
- **Enumerated → proxy on an EXISTING function needs a two-phase deploy.** Earlier deploys
  with enumerated routes may already have left the function's resource policy near the
  20 KB cap (dozens of statements). In an in-place update CloudFormation adds the new proxy
  permissions *before* it deletes the old ones. The transient union overflows and the stack
  rolls back, although the proxy steady state is tiny. You can't get there in one update:
  - **Phase 1:** deploy the API with a single MOCK method and NO Lambda-backed methods. All
    old permissions are dropped, and the API stays valid.
  - **Phase 2:** deploy the proxy and `/docs/*` onto the now-empty policy.

  Alternative: a one-time `aws lambda remove-permission` for every statement id, then
  deploy. This is needed only once.
- **Lambda memory: the 128 MB default starves the cold-start import.** FastAPI +
  pydantic-core + SQLAlchemy + heavier libraries (numpy, pillow, shapely…) need more than
  128 MB, and Lambda CPU scales with memory. Init exceeds the timeout, and **every request
  returns 502**. Logs show `INIT_REPORT … Status: timeout` and `Max Memory Used: 127 MB`.
  Set `memory_size` to 256 MB or more on the API and on any event Lambda that imports the
  same stack.
- **A database in a private network means the Lambda MUST be in the VPC.** Without VPC
  config the Lambda can't reach it: `psycopg2.OperationalError: connection … timed out`,
  **502 on DB endpoints only**. `/docs` still works, and that is the tell. Put every Lambda
  that touches the DB in the VPC: subnets and security group from your network stack or
  parameter store. Check that the DB security group admits the Lambda's subnets or SG on
  the DB port. If the VPC work lives on another unmerged branch, merge it into the
  migration branch first. The migration deploys the SAME stack and would otherwise strip
  the VPC config off the function.
- **Swagger is FastAPI's job.** Set `openapi_url/docs_url/redoc_url` under `/docs/*`. Expose
  them as public (`AuthorizationType.NONE`) API Gateway resources: explicit resources beat
  the greedy `{proxy+}`. Delete any separate "publish swagger" pipeline step.
- **Spec richness = typed signatures (step 5) + app-level metadata:**
  - **Tags.** Without them every route lands under `default`. Set `openapi_tags=[...]` on
    the app and `tags=[...]` on each `include_router(...)`. A single-file app passes
    `tags=` and `summary=` on each route decorator.
  - **Error responses.** Your handlers return **400**, but FastAPI auto-adds a **422** to
    every validated operation. Document 400/401/404 with a shared `responses=` dict, and
    strip 422 in a custom `app.openapi()`, so the doc matches the real contract.
  - **Metadata and ids.** Set `title/version/description/contact` and
    `servers=[dev, prod]`. Clean operationIds with
    `generate_unique_id_function=lambda route: route.name`; otherwise they get mangled to
    `get_x_path_get`. A `contact` email triggers a harmless `email-validator not installed`
    warning.
- **`isBase64Encoded` / binary** is a Mangum ↔ API Gateway concern that `TestClient` never
  exercises. Assert the returned bytes in tests, not that field.
- **`headers == HEADERS` exact-equality tests** can't hold under `TestClient`, which adds
  content-type and length. Relax them to a CORS-subset check. Return httpx's
  case-insensitive `Headers` from the test shim.
- **Don't pin exact-latest under a cooldown.** A release-age cooldown rejects releases
  younger than N days. Use lower bounds and let `uv.lock` capture the newest allowed version.
- **`cdk.json`** → `{"app": "uv run python cdk.py"}`. If the CI image lacks the cdk CLI,
  run `npm install -g aws-cdk@2` in the deploy step.
- **isort + git submodules in the lint step.** If the lint step doesn't check out
  submodules, isort can't detect shared libraries vendored as submodules as first-party.
  `--check-only` then fails on every file that imports them: it passes locally and fails in
  CI. Declare them: `[tool.isort] known_first_party = ["auth_lib", "shared_db"]`.

## Optional: flatten `src/chalicelib` → `src/`

Once the framework is gone, the `chalicelib` package name is legacy. Flattening it to the
`src` sources root is a clean follow-up. See `references/local-run.md`: it covers the
submodule `git mv` and `.gitmodules` handling and the local-run recipe.

## Verify

- `uv run pytest` green after each phase; `uv run isort --check-only` and `uv run ruff check`.
- `cdk.py` **imports** cleanly, which validates the alpha `PythonFunction` import and the
  syntax. A full `cdk synth` runs the real Docker bundle (minutes), so leave that to CI.
- Watch the first real deploy: PythonFunction bundling succeeds, the resource policy stays
  under 20 KB, and `/docs/openapi` is reachable without auth.
- **A green pipeline ≠ a working API. Check the deployed function at runtime**, because the
  killers here only surface after deploy:
  1. `/docs/openapi` returns 200. A 502 on *every* path, including docs, means memory/init.
  2. An authenticated DB-backed endpoint returns data. A 502 on DB paths only, while
     `/docs` works, means the Lambda isn't in the VPC.
  3. `aws lambda get-function-configuration` shows the expected `VpcConfig` and `MemorySize`.

  The two smoking guns in CloudWatch: `INIT_REPORT … Status: timeout` and
  `psycopg2 … connection timed out`.
- Optional end-to-end: run locally with uvicorn against a dev database
  (`references/local-run.md`).
