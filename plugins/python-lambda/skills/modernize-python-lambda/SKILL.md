---
name: modernize-python-lambda
description: >-
  Modernize a Python AWS Lambda project (Chalice or plain) to Python 3.14 + pydantic v2 +
  SQLAlchemy 2.0, moving from Pipenv to uv with a release-age cooldown, aws-cdk v1 → v2,
  ruff/isort linters, and a CI image with a current Node for the CDK CLI. Use this whenever the
  user wants to upgrade, modernize or "bring up to date" a Lambda or Chalice project: to
  Python 3.14, to uv, to pydantic v2, to SQLAlchemy 2.0, or to the latest aws-cdk. Use it
  EVEN IF they name only one of these (e.g. "just move this lambda to Python 3.14" or
  "switch us to uv"): on this stack the upgrades are coupled, and pulling one forces the
  others. Triggers on: migrate lambda to python 3.14, pipenv to uv, pydantic v1 to v2,
  sqlalchemy 1.x to 2.0, aws-cdk v1 to v2, modernize lambda, old chalice project.
---

# Modernizing a Python Lambda: Python 3.14 + pydantic v2 + SQLAlchemy 2.0 (uv, cdk v2)

## Why these upgrades are one job, not five

"Move to Python 3.14" sounds like a small change. On this stack it is not: **Python 3.14
forces the rest.**
- Lambdas written in 2019–2021 typically pin `pydantic==1.8.x` and `sqlalchemy==1.3.x`.
  Those don't build or import on 3.14: pydantic needs v2 and SQLAlchemy needs 2.0.
- aws-cdk v1 is end-of-life, so "latest aws-cdk" means v2 (`aws-cdk-lib`), which is a
  separate import rewrite.
- The aws-cdk v2 CLI needs a current Node LTS, so old CI images break too.

So "just bump the Python version" expands into **uv + Python 3.14 + pydantic v2 +
SQLAlchemy 2.0 + aws-cdk v2 + CI image**.

**Surface this to the user before starting** and confirm the scope. If the user already
asked for the full modernization, or you run without a user to ask, state the scope and
proceed. Also confirm the two things that genuinely change the plan and that you cannot
infer:

1. **Internal shared packages**: any in-house library the project depends on, vendored
   as a git submodule or installed from git or a private index.
   Newer releases usually support the new stack, but the project is almost certainly
   **pinned to an old revision** that doesn't. The job is to bump each pin to a compatible
   version, not to migrate their code. See Step 3.
2. **Branch and deploy expectations**: which branch to cut from, and whether pushing a
   branch auto-deploys. Don't push without asking (see "Committing").

## Sibling skills: reuse, don't reinvent

This skill is the *orchestrator*. The detailed rules live in the skills you invoke at
each step:

| Step | Skill | What it gives you |
|------|-------|-------------------|
| pydantic step | `pydantic-v2-migration` | validator → field_validator, BaseSettings → pydantic-settings, the Optional-default trap |
| SQLAlchemy step | `sqlalchemy-v2-migration` | positional `select()`, `Row.mappings()`, autocommit removal |
| cooldown | `dependency-cooldown` | `exclude-newer` (uv) or `min-release-age` (Poetry) |
| framework swap, if wanted | `chalice-to-fastapi` | Chalice → FastAPI on Mangum |

Generic migration guides assume Poetry or plain pip. **Here the target is uv**, so
translate their commands: `poetry add` → `uv add`, `python -m pytest` → `uv run pytest`.
The reference files in this skill record the *deltas* the generic skills don't cover.

## Order of operations

Do the steps in order and **verify after each one**: a green step is a safe base for the
next. Read the reference files when you reach their step:

- `references/uv-setup.md`: pyproject.toml, the cooldown, the requirements export;
- `references/pydantic-sqlalchemy-notes.md`: deltas beyond the two migration skills;
- `references/aws-cdk-v2.md`: the cdk.py rewrite and a synth check that needs no credentials;
- `references/ci-pipeline.md`: the CI image and pipeline.

### Step 0: Recon (before changing anything)

Understand the current shape, so you know how big the job is:

- Read `Pipfile`/`Pipfile.lock` (or the existing `pyproject.toml`), `cdk.py`,
  `.gitmodules`, `src/.chalice/config.json`, `Makefile` and the CI config.
- Grep for the patterns you will have to change, to size the blast radius:
  ```bash
  # pydantic v1 API
  grep -rnE "parse_obj|\.dict\(\)|\.json\(\)|BaseSettings|@validator|@root_validator|orm_mode|class Config|from_orm|json_encoders" src tests
  # Optional fields with no default: required in v2, the #1 silent break
  grep -rnE "^\s+\w+: Optional\[[^=]*$" src tests
  # SQLAlchemy 1.x patterns: list select, autocommit on connect, Row unpacking
  grep -rnE "select\(\[|\.connect\(\)|\*\*row" src tests
  # Chalice query params (see chalice-query-params-expand)
  grep -rnE "query_params|\.getlist" src
  ```
- Note the split between runtime and build deps. With Chalice, **chalice itself is a
  build/dev dep**: it vendors its own runtime into the package. Only true runtime deps
  (pydantic, sqlalchemy, a DB driver, a JWT library, …) go into `src/requirements.txt`.

### Step 1: Package manager + Python 3.14 + the cooldown → `references/uv-setup.md`

First find the current package manager and act on it:

- **Pipenv** (`Pipfile`/`Pipfile.lock`) → **migrate to uv**: create `pyproject.toml` and
  `.python-version` (`3.14`), run `uv lock` and `uv sync`, delete `Pipfile`/`Pipfile.lock`.
- **Poetry** (`pyproject.toml` with `[tool.poetry]` + `poetry.lock`) → stay on Poetry:
  bump `requires-python` and deps, re-lock. Don't force a uv migration on a Poetry repo
  unless the user asks.
- **uv already** → just apply the version bumps.

**A release-age cooldown is mandatory whatever the tool; only its spelling differs.** The
resolver ignores any release younger than N days (default 15), a buffer against freshly
published malicious versions. Set it **before the first `uv lock`/`poetry lock`**, so the
first lock already respects it:

- **uv:** `[tool.uv] exclude-newer = "15 days"` in `pyproject.toml`. The template in
  `references/uv-setup.md` already contains it.
- **Poetry:** `[solver] min-release-age = 15` in `poetry.toml`.

On an existing project, the `dependency-cooldown` script does this idempotently. On a
project you are moving off Pipenv, pass the target tool explicitly (`--tool uv`): auto-detection
finds neither uv nor Poetry yet.

Verify: `uv run python -c "import chalice"` (or the Poetry equivalent), and check that the
resolver actually uses Python 3.14.

### Step 2: pydantic v1 → v2 → `pydantic-v2-migration` + `references/pydantic-sqlalchemy-notes.md`

Migrate models, settings **and response/serialization models**. People forget the last
group (see the notes): it fails silently as a 4xx/5xx, not as a crash.

### Step 3: Bump internal shared packages to compatible versions

Internal shared packages carry their own pins on pydantic, SQLAlchemy and the Python
range. Recent releases usually support the new stack, but the project is likely stuck on
an **old revision that still pins pydantic 1.x or SQLAlchemy 1.x**. That old pin drags the
whole resolve back, or fails to import on 3.14. **Confirm that each one is bumped to a
compatible version; this is a required check, not an afterthought.** A single stale
internal pin silently brings pydantic v1 back into the tree.

**First enumerate them.** If there is no `.gitmodules` and no dependency from a source
other than PyPI, record "no internal packages" and go to Step 4. Non-PyPI sources show up
as:
`grep -nE "git\+|@ git|file:|path *=|index-url|\[\[tool.uv.index\]\]" pyproject.toml Pipfile uv.lock 2>/dev/null`.

They arrive in two ways:
- **Git submodules**: check `.gitmodules`. The pin is the checked-out commit.
- **Git or private-index dependencies**: grep `pyproject.toml`, `Pipfile*` and `uv.lock` for
  your organization's git host/index and the known package names. The pin is the
  version/tag/branch in `pyproject.toml`, or the resolved entry in `uv.lock`.

**For each package, verify, then bump:**
- Find the newest revision and read its declared support. For a submodule:
  `cd <path> && git fetch && git show origin/<default-branch>:requirements.txt` (and its
  `pyproject.toml`/`setup.py`, if present). Look for `pydantic>=2`, `sqlalchemy>=2` and a
  `requires-python` that includes 3.14. For a pyproject dependency, check the package's
  tags or index for the release that declares the same.
- **Bump the pin.** Submodule: `git checkout <compatible-commit>`; the submodule pointer
  change is committed in the parent repo. Pyproject dependency: raise the version/tag
  constraint, run `uv lock`, and confirm that `uv.lock` no longer pulls pydantic 1.x or
  SQLAlchemy 1.x anywhere.
- **Verify API compatibility.** Your code calls these packages, so a major bump can move a
  signature. Check that the functions, classes and fields you use still line up.
  `uv run pytest` and an import smoke test catch most of it.

Whatever you found, finish the step with the generic check: `uv.lock` resolves no
`pydantic` below 2 and no `sqlalchemy` below 2.

Consider migrating an internal package's *own* code only if no compatible release exists.
Then flag the cross-service impact: other services share it.

### Step 4: SQLAlchemy 1.x → 2.0 → `sqlalchemy-v2-migration` + notes

### Step 5: aws-cdk v1 → v2 → `references/aws-cdk-v2.md`

### Step 6: Linters (add them if missing)

**Only if ruff/isort aren't configured yet** (`grep -q "tool.ruff" pyproject.toml`).
Keep the rule set small: this step adds a gate, it doesn't restyle the codebase. Rewriting
annotations to `X | None` and similar upgrades (ruff `UP` rules) is a separate change, if
the team wants it.

```toml
[tool.ruff]
target-version = "py314"
line-length = 120                      # match the project's existing style
src = ["src", "tests"]
extend-exclude = ["out", "cdk.out"]    # + submodule paths

[tool.ruff.lint]
select = ["E", "F"]

[tool.isort]
profile = "black"
line_length = 120
src_paths = ["src", "tests"]
skip = ["out", "cdk.out", ".venv"]     # + submodule paths
```

- add them as dev deps: `uv add --dev ruff isort`;
- add `make lint` that only checks (`isort --check-only`, `ruff check`) and `make format`
  that rewrites (Makefile in `references/uv-setup.md`), plus a lint CI step;
- run `make format` once, and commit that churn separately from the migration.

If a long unbreakable literal trips `E501` (e.g. a token in a test fixture), add
`# noqa: E501` on that line instead of lowering the line length for everything.

### Step 7: CI image and pipeline → `references/ci-pipeline.md`

### Step 8: Verify end to end

- `uv run pytest`, on Python 3.14, with every test that passed before still passing.
- If the tests use an auth library: **make them environment-independent.** An auth library
  may check an environment-specific property of the test token, e.g. that its issuer
  region matches the deploy region, and return 401 on a mismatch. Don't paper over it by
  exporting a matching value. That is a trap: the tests then pass for one environment
  and fail for another. Instead, disable the check in an autouse fixture in
  `conftest.py`, so the tests pass on any branch and locally.
- `make lint` exits 0, and the package step (`chalice package`) succeeds; with Chalice,
  `out/sam.json` shows the `python3.14` runtime.
- CDK: an in-process synth with boto3 mocked (`references/aws-cdk-v2.md`). A real
  `cdk synth` needs credentials and real parameters.

## Committing

- Follow the project's commit-message convention; ask for the ticket id, don't invent one.
- Prefer **separate commits per concern** (migration / linters / pipeline), so the
  mechanical isort churn doesn't bury the real migration diff.
- **Do not push without asking.** Many pipelines deploy on push to the main development
  branch, often with `cdk deploy --require-approval never`. Let the user decide when.
- Add build artifacts to `.gitignore`: `.venv`, `out`, `cdk.out`, `*.env`, `.DS_Store`.

## Gotchas that actually bit

- **Don't pin exact-latest under a cooldown.** With `exclude-newer = "15 days"`, uv
  rejects any release younger than 15 days, so `pydantic==<today's latest>` can fail to
  resolve. Use lower bounds (`pydantic>=2.10`) and let the lockfile capture the newest
  allowed version.
- **pydantic Optional-without-default** is the #1 silent break, and it hides in response
  models, not only in request filters. `data: Optional[Any]` without `= None` becomes
  required in v2. You get a `ValidationError`, and your exception handler turns a 200 into
  a 4xx/5xx. Grep every `BaseModel`, not just the obvious ones.
- **SQLAlchemy `engine.connect()` stopped autocommitting.** Insert fixtures that used
  `with engine.connect()` silently persist nothing in 2.0. Use `engine.begin()`.
- **The aws-cdk v2 CLI needs a current Node LTS.** Check the supported range in the
  release notes of your CDK version. On Node 14, `cdk synth` crashes with
  `SyntaxError: Unexpected token '{'`. That is why the CI image changes. Confirm that
  `Runtime.PYTHON_3_14` exists in the resolved `aws-cdk-lib` before relying on it.
- **A stale internal-package pin silently drags pydantic v1 back in.** After bumping the
  internal packages, grep `uv.lock` and confirm that nothing still resolves `pydantic <2`
  or `sqlalchemy <2`. One old transitive pin poisons the resolve, and the failure looks
  like an unrelated import or validation error at runtime.
- **Keep the pipeline lean once the image is right.** If the image already provides Python
  3.14, uv and Node, delete hand-rolled steps that install them: `curl … uv/install.sh`,
  `uv python install`, Node version managers. Check out git submodules only in steps that
  import runtime code (tests, package, deploy). The lint step doesn't need them.
