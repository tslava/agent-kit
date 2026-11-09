# Packaging, CDK and pipeline (Phases C and D)

Once Chalice is gone, `chalice package` no longer vendors the runtime. **Use `PythonFunction`
from `aws_cdk.aws_lambda_python_alpha`**: CDK bundles the code and pip-installs
`src/requirements.txt` inside a Lambda-matching Docker image at deploy time. Do **not**
hand-roll a build script with `Code.from_asset(zip)`. Cross-installing manylinux wheels and
zipping them works, but it is extra machinery the platform already provides, and some CI
images don't even ship `zip`.

## cdk.py: a PythonFunction per Lambda

```python
from aws_cdk import Duration
from aws_cdk import aws_lambda as lambda_
from aws_cdk.aws_lambda_python_alpha import PythonFunction

api_fn = PythonFunction(
    self, "InventoryApiLambda", function_name="InventoryApi",
    entry="src",            # sources root: requirements.txt + the app + submodules
    index="app.py",         # module within entry
    handler="handler",      # the Mangum callable: handler = Mangum(app)
    runtime=lambda_.Runtime.PYTHON_3_14,
    memory_size=256,        # see "memory" below
    timeout=Duration.seconds(25),
    environment=env,
    **vpc_kwargs,           # see "VPC" below
)
# Event/cron Lambdas share the same entry with a different index/handler,
# e.g. index="worker.py", handler="handle_event".
```

- `entry="src"` must contain `requirements.txt`. Export it in the pipeline (below):
  PythonFunction pip-installs it into the bundle. Submodules under `src/` are bundled
  automatically.
- Add `aws-cdk-aws-lambda-python-alpha` to the dev deps. It **must match `aws-cdk-lib`
  exactly** (the same jsii binding). Give both the same lower bound and let `uv lock`
  resolve them to the same version (e.g. `2.x.0` and `2.x.0a0`). A mismatch fails at import.
- **Bundling needs Docker** and pulls the SAM build image for your Python version. A local
  `cdk synth` triggers the real Docker build (minutes: image pull + pip install). For a
  quick local check, just **import `cdk.py`**: that validates the alpha import and the
  syntax. Let CI do the real bundle.
- `runtime`: check that the constant exists (`hasattr(lambda_.Runtime, "PYTHON_3_14")`)
  *and* that the managed runtime is GA in your regions. Otherwise use the previous version.
- **Memory: `memory_size` ≥ 256** on the API Lambda and on any event Lambda that imports
  the app stack. With the 128 MB default, a heavy import (FastAPI + pydantic-core +
  SQLAlchemy + numpy/pillow/…) doesn't finish within the init window, because CPU scales
  with memory. You get `INIT … Status: timeout` and 502 on every request. Measure your own
  cold start after the change.
- **VPC**: if the database is in a private network, every Lambda that touches it must be in
  the VPC. Read the VPC id, private subnets and Lambda security group from your network
  stack or parameter store and pass them as `vpc`/`vpc_subnets`/`security_groups`. Without
  that you get `psycopg2 … connection timed out` and 502 on DB endpoints, while `/docs`
  works. The migration deploys the SAME stack. If the VPC config lives on a separate
  unmerged branch, MERGE it first, or the deploy strips the VPC off the function. Check
  that the DB security group admits the Lambda on the DB port.
- `cdk.json`: `{"app": "python3 cdk.py"}` → **`{"app": "uv run python cdk.py"}`**.

## API Gateway: a catch-all proxy, NOT enumerated routes

FastAPI + Mangum route internally, so API Gateway needs only one catch-all. **Don't
enumerate every path with `add_resource`/`add_method`.** Each method makes CDK emit ~2
`AWS::Lambda::Permission`s, and ~20 routes overflow the Lambda **resource-policy hard limit
of 20480 bytes**. The deploy fails with
`The final policy size (NNNNN) is bigger than the limit (20480)`. Instead:

```python
from aws_cdk import aws_apigateway as apigateway

api = apigateway.LambdaRestApi(
    self, "InventoryApi", handler=api_fn, proxy=False,
    deploy_options=apigateway.StageOptions(stage_name="v1"),
    binary_media_types=["application/zip"],   # keep for zip downloads
    default_cors_preflight_options=cors_options,
)

# ONE proxy method for everything, protected by your authorizer. CORS preflight comes
# from default_cors_preflight_options; binary downloads flow through here too.
api.root.add_proxy(default_method_options=apigateway.MethodOptions(**auth))
```

One proxy method needs only a handful of permissions. Switching an existing function from
enumerated routes to the proxy may need a two-phase deploy (see SKILL.md).

## Swagger: served by FastAPI, exposed as public /docs/* resources

FastAPI generates the OpenAPI UI, so there is **no separate "publish swagger" pipeline
step** and no `swagger.yaml` to upload. In `app.py`, nest the docs under `/docs`, so one API
Gateway subtree covers them:

```python
app = FastAPI(title="...", openapi_url="/docs/openapi.json",
              docs_url="/docs/openapi", redoc_url="/docs/redoc")
```

In `cdk.py`, expose them as **public** resources. Explicit resources take precedence over
the greedy `{proxy+}`, so the docs stay unauthenticated while everything else is protected:

```python
docs = api.root.add_resource("docs")
for p in ("openapi", "openapi.json", "redoc"):
    docs.add_resource(p).add_method("GET", authorization_type=apigateway.AuthorizationType.NONE)
```

Delete the old swagger publishing step. Whether to keep or remove `swagger.yaml` is the
user's call.

## CI pipeline (Phase D)

Deltas from a Chalice pipeline. The examples are generic, adapt them to your CI:

- **Image**: one with your Python version, Node (for the cdk CLI) and uv. If the cdk CLI
  isn't in the image, add `npm install -g aws-cdk@2` to each deploy step.
- **Auth**: prefer keyless OIDC federation to AWS over static access keys.
- **Lint step**: `uv sync --frozen`, `uv run isort --check-only`, `uv run ruff check`. If
  this step doesn't check out submodules, declare them as first-party for isort (below).
- **Test step**: check out submodules, `uv sync --frozen`, `uv run pytest`.
- **Deploy step**:
  1. auth;
  2. check out submodules;
  3. `uv sync --frozen`;
  4. `uv export --no-dev --no-hashes --no-emit-project -o src/requirements.txt` (the bundle input);
  5. install the cdk CLI if needed;
  6. `cdk deploy <StackName> --require-approval never`.

  **Enable a Docker service**, because PythonFunction bundles in Docker. No
  `chalice package`, no build script.
- `.gitignore`: add `.venv`, `cdk.out`, local `*.env` files and any CI token files.

### isort + submodules in the lint step

If the lint step doesn't check out submodules, isort can't detect the submodule packages as
first-party from `src_paths` and sorts them as third-party. `isort --check-only` then fails
on every file that imports them, even though it passes locally where the submodules exist.
Fix: `[tool.isort] known_first_party = ["auth_lib", "shared_db"]`. This bites hardest after
flattening `chalicelib/`, because those packages become top-level import roots.

## pyproject.toml: the dependency split

- **Runtime** (`[project.dependencies]`, bundled and exported): `fastapi`, `mangum`, plus
  what the app imports at runtime (sqlalchemy, pydantic, pydantic-settings, a DB driver,
  sentry-sdk, …).
- **Dev** (`[dependency-groups] dev`): `aws-cdk-lib`, **`aws-cdk-aws-lambda-python-alpha`**
  (matched version), `constructs`, `boto3`, `httpx` (for TestClient), `pytest`, `ruff`,
  `isort`, type checkers. **No chalice.**
- A cooldown (`[tool.uv] exclude-newer`, see `dependency-cooldown`), lower-bound
  versions, and `uv.lock` pins the exact ones.
