# aws-cdk v1 → v2 (aws-cdk-lib)

CDK v1 (`aws-cdk-core`, `aws-cdk.aws-*` packages) is end-of-life. "Latest aws-cdk" means
v2: a single `aws-cdk-lib` package + `constructs`. The migration is mostly imports.

## cdk.py import rewrite

```python
# v1
from aws_cdk import aws_lambda as lambda_, core, aws_apigateway as apigateway, aws_ssm as ssm
from aws_cdk.core import Duration, Environment

class Stack(core.Stack):
    def __init__(self, app: core.App, id, env): super().__init__(app, id, env=env)
```
```python
# v2 — the old `core` is now the top-level aws_cdk namespace; Construct comes from constructs
from aws_cdk import (
    App, Duration, Environment, Stack,
    aws_lambda as lambda_, aws_apigateway as apigateway, aws_ssm as ssm,
)
from constructs import Construct

class InventoryApiStack(Stack):
    def __init__(self, scope: Construct, id: str, env): super().__init__(scope, id, env=env)
```

Other concrete changes seen in practice:
- `core.App()` → `App()`; `core.Stack` → `Stack`; `core.Duration`/`core.Environment` →
  top-level `Duration`/`Environment`.
- **`lambda_.Code.asset(...)` → `lambda_.Code.from_asset(...)`** (the v1 alias is gone).
- **`runtime=lambda_.Runtime.PYTHON_3_9` → `PYTHON_3_14`.** Verify the enum member exists
  in the resolved aws-cdk-lib (it does in recent 2.2xx): `hasattr(lambda_.Runtime,
  "PYTHON_3_14")`.
- `apigateway.LambdaRestApi`, `DomainName`, `CfnAuthorizer`, `MockIntegration`,
  `StageOptions`, `Certificate.from_certificate_arn`, `node.find_child(...)
  .add_property_override(...)` all exist unchanged in v2.
- Point `cdk.json` at the uv environment so the CLI runs the app with aws-cdk-lib
  installed: `{"app": "uv run python cdk.py"}`.

## Synth check without AWS creds

**This check needs Node too.** CDK's Python package is a jsii binding: even
`from aws_cdk import aws_lambda` starts a `node` process. Without Node on PATH you get
`FileNotFoundError: [Errno 2] No such file or directory: 'node'`, followed by a noisy
`AttributeError` about `_NodeProcess`. Use a Node version that your aws-cdk-lib release
supports. If the machine has no Node and you can't install one globally, a Node from PyPI
works for this check: `uv run --with nodejs-wheel-binaries python …`.

A real `cdk synth` calls SSM (`boto3 … get_parameter`) and needs creds + the params to
exist. To validate the construct graph locally, mock boto3 and synth in-process — this
also confirms jsii runs on Python 3.14 and that the asset path resolves:

```python
# after `make lambda` has produced out/deployment.zip
STACK_REGION=us-east-1 uv run python - <<'PY'
import importlib.util
from unittest import mock
fake = mock.MagicMock()
fake.get_parameter.return_value = {"Parameter": {"Value": "x"}}
with mock.patch("boto3.client", return_value=fake):
    spec = importlib.util.spec_from_file_location("cdk_mod", "cdk.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    app = m.App()
    m.InventoryApiStack(app, "InventoryApi", env=m.Environment(region="us-east-1"))
    res = app.synth().get_stack_by_name("InventoryApi").template["Resources"]
    fn = next(r for r in res.values() if r["Type"] == "AWS::Lambda::Function")
    print("SYNTH OK, runtime:", fn["Properties"]["Runtime"])
PY
```

Expect `runtime: python3.14`. If it fails with `CannotFindAsset out/deployment.zip`, run
`make lambda` first — that's the chalice package the Lambda construct references.

## The CLI needs a current Node LTS

The aws-cdk **v2 CLI** (`npm i -g aws-cdk@2`) requires a supported Node LTS (check the release notes of your CDK version). Under Node 14 it dies
with `SyntaxError: Unexpected token '{'`. This is why the CI image has to change (see `ci-pipeline.md`).
