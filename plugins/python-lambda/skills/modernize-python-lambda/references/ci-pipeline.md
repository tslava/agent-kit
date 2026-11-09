# CI image and pipeline

The examples use Bitbucket Pipelines syntax. The same steps map one to one onto GitHub
Actions or GitLab CI.

## The image does the heavy lifting

Use one CI image that ships the whole toolchain: **Python 3.14, uv and a current Node
LTS**. Node is the point: the aws-cdk v2 CLI and the `aws_cdk` Python package (jsii) both
need a supported Node version (check your CDK release notes). An older image with Node 14
crashes `cdk synth` with `SyntaxError: Unexpected token '{'`.

Public uv images such as `ghcr.io/astral-sh/uv:python3.14-bookworm` have Python and uv but
no Node. Two ways to get all three:

- **Build a small image once** and push it to your registry (a starting point, adjust and
  pin versions):
  ```dockerfile
  FROM ghcr.io/astral-sh/uv:python3.14-bookworm
  RUN apt-get update \
   && apt-get install -y --no-install-recommends git curl ca-certificates \
   && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
   && apt-get install -y --no-install-recommends nodejs \
   && npm install -g aws-cdk@2 \
   && rm -rf /var/lib/apt/lists/*
  ```
- **Or use the uv image and install Node only in the deploy step** (slower, but no image to
  maintain): `curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && apt-get install -y nodejs`.

Once the image provides a tool, **delete the hand-rolled steps that install it**:

- ❌ `curl -LsSf https://astral.sh/uv/install.sh | sh` + `export PATH=$HOME/.local/bin:$PATH`
- ❌ `uv python install 3.14`
- ❌ Node version managers (`npm install -g n && n 20 && hash -r`, …), if the image has Node

Keep `npm install -g aws-cdk@2` if the CLI is *not* in the image. Check out git submodules
only in steps that import runtime code (tests, package, deploy). The **lint step doesn't
need submodules**: ruff and isort exclude them and don't import anything.

Prefer keyless OIDC federation to AWS over static access keys stored as CI variables.
`cdk synth` and `cdk deploy` need those credentials when `cdk.py` reads parameters or
looks up resources.

## Example pipeline (lint → test → package/deploy)

Trim it to the project: drop the Postgres service if the tests use SQLite, drop the
`docker` service unless something bundles in Docker, and keep only the deployment
branches you have.

```yaml
image: <YOUR_CI_IMAGE>          # Python 3.14 + uv + current Node LTS

definitions:
  services:
    postgres:
      image: postgres:17
      environment:
        POSTGRES_DB: testdb
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: postgres   # throwaway, test container only
  steps:
    - step: &lint
        name: Lint
        script:
          - uv sync --locked
          - uv run isort --check-only src tests
          - uv run ruff check src tests
    - step: &test_and_deploy
        name: Test and deploy
        services: [postgres, docker]
        script:
          - git submodule update --init --recursive
          - uv sync --locked
          - uv export --no-dev --no-hashes --no-emit-project -o src/requirements.txt
          - uv run pytest
          - cd src; uv run chalice package ../out; cd -
          - npm install -g aws-cdk@2      # if the CLI isn't in the image
          - cdk synth > /dev/null
          - cdk deploy --require-approval never

pipelines:
  default:
    - step: *lint
    - step:
        name: Test
        services: [postgres]
        script:
          - git submodule update --init --recursive
          - uv sync --locked
          - uv run pytest
  branches:
    develop:
      - step: *lint
      - step: {deployment: Development, <<: *test_and_deploy}
    main:
      - step: *lint
      - step: {deployment: Production, <<: *test_and_deploy}
```

Notes:
- Don't make tests depend on the deploy environment. If your auth library checks an
  environment-specific claim of the test token, disable that check in `conftest.py`.
  Exporting a matching value makes the tests pass for one environment and fail for the
  other (see SKILL.md, Step 8).
- `uv sync --locked` fails if `uv.lock` is stale, which is a useful reproducibility gate.
- Validate the YAML after editing it:
  `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('bitbucket-pipelines.yml'))"`.
- If the API docs used to be published by a separate pipeline step (copying a
  `swagger.yaml` somewhere), keep it as is during this migration. With `chalice-to-fastapi`,
  FastAPI serves the docs and that step goes away.
