# CI/CD and supply-chain checklist

## Deploy credentials

- Long-lived cloud keys stored as CI variables. Prefer OIDC federation: the CI job exchanges a
  short-lived token for a role, and nothing permanent is stored.
- With OIDC, read the role's trust policy. It must pin the repository and, for deploy roles, the
  branch or environment. Check the actual subject condition: a pattern such as `repo:my-org/*`,
  or one with no branch or environment part, lets more repositories or refs assume the role
  than intended.
- Deploy roles with administrator rights "because CDK needs it". Scope them to the stacks and
  services they deploy.

## GitHub Actions

- `pull_request_target` and `workflow_run` workflows run with the base repository's secrets and
  a write-capable token. They become exploitable when they check out, build or run code from
  the pull request, or artifacts it produced.
- Script injection: `${{ github.event.* }}` values (issue titles, PR bodies, branch names)
  interpolated directly into `run:`. Pass them through `env:` and quote the variable.
- No `permissions:` block at workflow or job level: the token then gets the repository or
  organization default, which may be write-all. Check what that default is.
- Third-party actions referenced by a mutable tag instead of a full commit SHA.
- Secrets printed by debug steps, or uploaded inside build artifacts.

## Other CI systems

The same questions apply to Bitbucket Pipelines, GitLab CI and CodeBuild: where deploy
credentials come from, whether pipelines for forks or pull requests can read them, and whether
untrusted text reaches a shell.

## Dependencies

- No lock file, or a lock file that CI doesn't enforce (installing from version ranges instead
  of `uv sync --locked`, `npm ci`, `poetry install` from `poetry.lock`).
- Packages resolved the day they are published. A release cooldown (uv `exclude-newer`, Poetry
  `min-release-age`, the `dependency-cooldown` skill in this marketplace) gives the ecosystem
  time to catch a compromised release before you install it.
- A private index combined with a public one. With pip's `--extra-index-url` the resolver
  considers both indexes, so an attacker can publish a higher version of your internal package
  name on the public one (dependency confusion). uv stops at the first index that has the
  package by default (`first-index`); check whether `index-strategy` was changed to
  `unsafe-best-match`.
- Install-time scripts (`postinstall`, `setup.py` with side effects) from packages that don't
  need them.
- Known CVEs: check the versions in the lock file, not the ranges in the manifest, and say
  whether the vulnerable code path is used.

## Containers

- Images running as root, base images referenced by a moving tag, secrets copied into a layer
  and deleted in a later one (they stay in the earlier layer).
