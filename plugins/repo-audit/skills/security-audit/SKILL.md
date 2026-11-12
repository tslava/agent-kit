---
name: security-audit
description: Security review of a whole repository - code, config, infrastructure-as-code, CI/CD, dependencies, secrets and AI coding-agent configuration - with a threat model, a findings table where every Critical/High finding has survived an attempt to disprove it, and a remediation plan. Use when the user asks for a security review, security audit, threat model, "is this repo safe to open-source", "check this service for vulnerabilities", or a hardening pass, EVEN IF they name only one area (e.g. "check our GitHub Actions", "are there secrets in here", "review the IAM in this CDK app", "is our .claude/settings.json too permissive"). Not for reviewing only the pending changes on a branch (Claude Code's built-in /security-review does that), not for a bug-hunting code review, and not for fixing findings without being asked.
---

# Security audit

Goal: a short list of real, exploitable issues in *this* repository, each tied to a file and
line, ranked by risk, with a concrete fix. A review that lists twenty generic risks is worse
than one that lists three true ones: the reader has to verify every line, and stops trusting
the report after the first false alarm.

## Ground rules

- **Read-only.** Don't change code, don't run anything against real systems, don't call
  external services with credentials found in the repo. Proofs of concept are local tests.
- **Never print a secret value.** If you find one, report the file, line and kind of secret,
  and write the value as `***`. Never put the secret itself into a command. To see how long it
  has been in git history, use `git log --oneline -- <file>` or search for the variable name next
  to it with `git log --oneline -S <name>`: `--oneline` lists commits without printing diffs.
- **Evidence or nothing.** Every finding cites `file:line` and a short excerpt. If the risk
  depends on something outside the repo (cloud console settings, an API Gateway authorizer
  configured elsewhere), mark it **[Needs confirmation]** and say exactly what to check.
- **Don't invent.** No technologies, files or tools that aren't in the repo. If the repo has no
  meaningful attack surface, say so.

## 1. Reconnaissance

Read before judging. Summarize in a few lines:

- languages, frameworks, entry points and exposed interfaces (HTTP routes, Lambda handlers,
  queue consumers, cron jobs, CLIs, webhooks, admin and debug endpoints);
- the authentication and authorization model, and *where it lives*: in code, in middleware, or
  in infrastructure (API Gateway authorizers, IAM, a load balancer, a VPN);
- data stores and external integrations;
- how secrets reach the code: env vars, files, CI variables, a parameter store or vault;
- how code reaches production: CI system, deploy credentials, IaC.

## 2. Threat model

Keep it to one screen:

- **Assets:** what is worth stealing or breaking here.
- **Actors:** anonymous user, authenticated user, another tenant, an insider, a compromised
  dependency, a malicious pull request, text an AI agent reads.
- **Entry points:** ranked by exposure.
- **Abuse cases:** 3–5 scenarios specific to this project, not to "web apps in general".

## 3. Look for issues

Go through the categories that apply. The references hold stack-specific checklists; read the
ones that match what reconnaissance found.

- **AuthN/AuthZ:** missing or bypassable checks, object access by id without an ownership
  check, admin or debug routes left open, privilege escalation.
- **Injection:** SQL/NoSQL, shell, template, SSRF, path traversal, header injection.
- **Secrets and crypto:** hardcoded keys and tokens (including tests, notebooks, fixtures and
  git history), weak algorithms, JWTs without signature or audience checks.
- **Web/API:** CORS, CSRF, open redirects, upload handling, mass assignment, missing limits on
  payload size and page size.
- **Cloud and IaC:** see [references/aws-serverless.md](references/aws-serverless.md).
- **CI/CD and supply chain:** see [references/ci-supply-chain.md](references/ci-supply-chain.md).
- **AI coding-agent configuration:** see [references/ai-agent-config.md](references/ai-agent-config.md).
  Check it whenever the repo has `.claude/`, `.mcp.json`, `AGENTS.md`, `CLAUDE.md`, `.cursor/`,
  or scripts and workflows that run an agent CLI.
- **Logging:** secrets or personal data in logs, stack traces returned to clients.
- **Resilience:** unbounded concurrency, missing timeouts, ReDoS, queue flooding.

## 4. Try to disprove every Critical and High finding

Before a finding goes into the table, argue against it:

- Is the code reachable from an attacker's position, or only from a trusted caller?
- Does a check exist somewhere else: middleware, a decorator, a base class, an API Gateway
  authorizer, an IAM condition, a network boundary? Handlers on Lambda often look unprotected
  because authorization lives in the gateway config.
- Is the "secret" a placeholder, a public key, a test fixture against a local container?
- Is the dependency version actually installed (check the lock file, not the manifest range)?

Keep the finding if it survives. Downgrade it, or mark it **[Needs confirmation]**, if the
answer depends on something you can't see. Drop it if it's disproved, and mention it in one line
under "Checked and ruled out" so the reader knows it was considered.

## 5. Report

Reply in the user's language.

**Findings**

| ID | Severity | Category | Location | Issue | Exploit scenario | Fix | Effort |
|----|----------|----------|----------|-------|------------------|-----|--------|

Severity: Critical / High / Medium / Low. Effort: S / M / L. Order by severity, then by effort.

**Checked and ruled out:** one line each.

**Remediation plan:** at most ten items, split into quick wins and changes that need design
work. Recommend tooling (secret scanning, dependency scanning, SAST, IaC scanning) only where
the repo lacks it, and say where it runs: pre-commit, CI, or on a schedule.

**Validation:** for the top three findings, a minimal local test that shows the vulnerable
behavior and passes once fixed, plus a short checklist to rerun after remediation.
