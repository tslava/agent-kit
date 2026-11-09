# Running locally + flattening chalicelib

## Run the FastAPI app locally

FastAPI has no built-in Lambda server. Run it with uvicorn, ephemerally, without adding a
dependency:

```bash
set -a; . ./env.local; set +a          # your local settings + temporary cloud credentials
uv run --with uvicorn uvicorn app:app --app-dir src --host 127.0.0.1 --port 8000
```

`/docs` (Swagger UI) is a free bonus over Chalice. Call endpoints with the same auth header
your clients send.

### A database in a private network: use a tunnel

If the app times out reaching the database, the DB is not publicly reachable. Open a tunnel
and point the app at it. On AWS, one option is Session Manager port forwarding through a
bastion instance:

```bash
aws ssm start-session --target <BASTION_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "host=<DB_HOST>,portNumber=5432,localPortNumber=15432"

# in another terminal
export DATABASE_HOST=localhost DATABASE_PORT=15432
uv run --with uvicorn uvicorn app:app --app-dir src --host 127.0.0.1 --port 8000
```

This needs `session-manager-plugin` locally. Use a read-only or disposable DB user if you
have one. A shared database is never "safe": treat writes as real. Temporary credentials
expire; re-authenticate when the tunnel calls start failing.

### Verify direct invocation through Mangum

Other services may invoke the Lambda directly instead of through API Gateway. To confirm
that works without an adapter, call `app.handler(event, None)` in-process with an event
shaped the way your callers build it, e.g.:

```python
event = {
    "httpMethod": "GET", "path": "/orders", "resource": "/{proxy+}",
    "requestContext": {"resourcePath": "/{proxy+}", "httpMethod": "GET"},
    "headers": {"Authorization": "<test token>"},
    "queryStringParameters": {"ids": "1,2"},
}
```

Try `queryStringParameters` as `{"id": 7}` (int), `{"ids": [1, 2]}` (list) and
`{"ids": "1,2"}` (comma string). Each should return 200 and validate. If your auth library
has environment-specific checks, disable them for this run (see `testing.md`).

## Flatten `src/chalicelib` → `src/` (optional follow-up)

Once the framework is gone, `chalicelib` is a legacy package name. Flatten it to the `src`
sources root, so modules import as `from utils import ...` instead of
`from chalicelib.utils import ...`.

1. **Move with `git mv`**, which preserves history:
   - each loose module (`db.py`, `models.py`, `utils.py`, `settings.py`, …) → `src/`;
   - packages (`routers/`, vendored clients) → `src/`;
   - submodules (e.g. `auth_lib`, `shared_db`) → `src/`.

   Drop `chalicelib/__init__.py`: `src` is a sources root, not a package.
2. **Submodules.** `git mv src/chalicelib/auth_lib src/auth_lib` updates the **path** in
   `.gitmodules` and keeps the pinned commit. The submodule **section name**
   (`[submodule "src/chalicelib/auth_lib"]`) keeps the old string. That is only a label:
   git resolves through the path, and `git submodule status` works. Renaming the section
   means editing `.git/config` and moving `.git/modules/<name>`. That is risky, so skip it.
3. **Rewrite imports** across `src/` (except submodules and vendored code), `tests/` and
   `cdk.py`:
   - `from chalicelib.<x> import …` → `from <x> import …`;
   - `from chalicelib import (a, b, …)` → one `import a` line per name. A single
     `import a, b` trips ruff E401;
   - `import chalicelib.<x> as y` → `import <x> as y`;
   - handler strings in `cdk.py`: `chalicelib.worker.*` → `worker.*`.

   Then run `uv run isort src tests` and `uv run ruff check --fix src tests`.
4. **Update paths** in:
   - ruff/isort excludes and `known_first_party` in `pyproject.toml`;
   - the CI config (any `cd src/<submodule>`);
   - `.gitignore` and docs, including stale docstrings.

   `PythonFunction` uses `entry="src"`, so it picks up the flattened layout without changes.
5. **Verify:**
   - `git status` shows renames (R/RM);
   - `uv run pytest` is green;
   - the app and the event handlers import;
   - `cdk synth` shows the correct handlers;
   - the bundle has no `chalicelib/` entries.
