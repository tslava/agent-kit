# AWS and serverless checklist

Read the IaC (CDK, SAM, Serverless Framework, Terraform, CloudFormation) together with the
handler code: on serverless most access control lives in the infrastructure.

## Entry points

- **API Gateway:** which routes have an authorizer (JWT or user pool, Lambda authorizer, IAM) and which
  don't. Authorization is set per method or route. A catch-all `{proxy+}` route sends every path
  without a more specific route to one integration under that method's setting, so endpoints
  added later in code are covered, or exposed, by it without any infrastructure change.
  API keys identify a client for usage plans; they are not authentication.
- **Lambda function URLs** with `AuthType: NONE` are public endpoints.
- **Lambda resource policies:** a principal of `*` or a service principal without a
  `SourceArn`/`SourceAccount` condition lets other accounts invoke the function.
- **Direct invocation:** functions called by other functions get their input from inside the
  account. If the payload contains user-controlled fields, the callee still has to validate them.

## IAM

- `Action: "*"`, `Resource: "*"`, or service-wide wildcards (`s3:*`, `dynamodb:*`) on execution
  roles. A compromised function gets everything its role allows.
- `iam:PassRole` with `Resource: "*"`: lets a role hand a more powerful role to a new resource.
- Roles shared by many functions: the least protected function sets the blast radius.
- Trust policies that any principal in the account, or any external account, can assume.

## Secrets

- Lambda environment variables are encrypted at rest, but anyone with
  `lambda:GetFunctionConfiguration` on the function reads them in clear. When IaC sets them from
  literal values, the secret also sits in the repository and in synthesized templates. Prefer a
  parameter store or secrets manager read at runtime, with the read permission scoped to that
  one parameter.
- CloudFormation parameters without `NoEcho` are shown in stack descriptions; `NoEcho` does not
  mask values copied into `Metadata` or outputs. Secrets passed as CDK context end up in
  `cdk.context.json` or the synthesized template.
- Docker build args can be read back from image history or build provenance. Use build secrets
  (`docker build --secret`) instead.

## Data and network

- S3 buckets without Block Public Access, with public ACLs, or with policies granting
  `Principal: "*"`.
- RDS or other databases with `PubliclyAccessible: true`, or security groups open to
  `0.0.0.0/0` on database, SSH or admin ports.
- Database access by a long-lived password where IAM database authentication would do.
- Encryption at rest switched off where the service allows it, and plain HTTP endpoints.

## Logging

- Request or event payloads logged in full: they often carry tokens, cookies or personal data.
- Log groups without retention keep that data forever.
