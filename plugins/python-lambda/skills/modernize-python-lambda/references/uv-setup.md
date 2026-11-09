# uv + Python 3.14 setup (replacing Pipenv)

## pyproject.toml template

Split deps by where they run:
- **runtime** deps are bundled into the Lambda and exported to `src/requirements.txt`
  for `chalice package`;
- **dev** deps are build/test only. chalice, aws-cdk, boto3, pytest and the linters are
  dev: chalice vendors its own runtime into the deployment package, and cdk/boto3 are only
  used for synth and deploy.

Copy only the lines the project actually uses. Every dependency below is an example.

```toml
[project]
name = "inventory-api"
version = "0.1.0"
description = "…"
requires-python = ">=3.14"
# Runtime deps bundled into the Lambda. Exported to src/requirements.txt.
dependencies = [
    "pydantic>=2.10",
    "pydantic-settings>=2.7",   # if the project uses BaseSettings (moved here in v2)
    "sqlalchemy>=2.0",
    # "psycopg2-binary>=2.9",   # if the project talks to Postgres
    # "python-jose>=3.3",       # if the project decodes JWTs
]

[dependency-groups]
dev = [
    "chalice>=1.32",            # if the project is a Chalice app
    "aws-cdk-lib>=2,<3",        # lower bound = the version you start from; uv.lock pins it
    "constructs>=10,<11",
    "boto3",
    "pytest",
    "ruff",
    "isort",
]

[tool.uv]
package = false                 # it's an app, not a library: don't build a wheel
exclude-newer = "15 days"       # supply-chain cooldown (see the dependency-cooldown skill)

[tool.pytest.ini_options]
pythonpath = ["src"]            # replaces the old PYTHONPATH=src in Makefile/pipeline
testpaths = ["tests"]           # keeps a submodule's own tests out of collection
```

The cooldown is already in this template. If you write it here, you don't need to run the
`dependency-cooldown` script as well.

**Use lower bounds, not `==latest`.** The `exclude-newer` cooldown refuses any release
younger than 15 days, so an exact pin to today's newest version can be unsatisfiable.
Lower bounds let uv pick the newest *allowed* version; `uv.lock` records the exact result.
When you check PyPI for the latest version, expect the lock to land a notch behind
"latest" for anything released in the last 15 days. That is correct.

**`sqlalchemy>=2.0` resolves to the newest 2.x**, which may be 2.1 or later. The 2.0-style
API that `sqlalchemy-v2-migration` teaches is what 2.x expects. If something fails that
the guide doesn't explain, read the changelog of the resolved minor version, or pin
`<2.1` for this migration and bump the minor version in a separate commit.

**Chalice picks the Lambda runtime from the interpreter it runs under.**
`.chalice/config.json` has no runtime field, so the Python in your CI image decides
whether the deployed Lambda is `python3.14`. Check `out/sam.json` after `chalice package`.

## Commands

```bash
uv python pin 3.14                 # writes .python-version
uv lock                            # resolves under the cooldown -> uv.lock
uv sync --dev                      # creates .venv with runtime + dev deps
rm -f Pipfile Pipfile.lock         # or `git rm` if they are tracked

# regenerate the chalice bundle's requirements (runtime deps only, fully pinned):
uv export --no-dev --no-hashes --no-emit-project -o src/requirements.txt
```

Commit `pyproject.toml`, `uv.lock`, `.python-version` and the regenerated
`src/requirements.txt`.

## Makefile (uv form)

`lint` only checks and fails on problems, the way CI runs it. `format` rewrites files.
Include root-level Python files such as `cdk.py`.

```make
test:
	uv run pytest

lint:
	uv run isort --check-only src tests cdk.py
	uv run ruff check src tests cdk.py

format:
	uv run isort src tests cdk.py
	uv run ruff check --fix src tests cdk.py

requirements:
	uv export --no-dev --no-hashes --no-emit-project -o src/requirements.txt

lambda: requirements
	cd src && uv run chalice package ../out
```

## Verify

```bash
uv run python -c "import chalice, sqlalchemy, pydantic; print('ok', pydantic.VERSION)"
```
