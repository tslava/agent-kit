---
name: readme-refresh
description: Audit a repo's README.md against the actual code and bring it up to date — fix inaccurate values, drop or mark stale information, add what is missing (env vars, entry points, message routing, background jobs, local dev commands). Use whenever the user asks to update, refresh, actualize, audit or "check for inaccuracies" in a README, EVEN IF they name only one concrete fix (e.g. "change Default 10 to 24 in the README and check the rest"). Triggers on: актуализируй ридми, обнови README, проверь ридми на неточности, устаревшая информация в README, readme is outdated, sync README with code, fix README defaults. NOT for writing CLAUDE.md (use /init) or for post-feature doc notes (use update-docs).
---

# README refresh

Goal: every statement in the README is true for the current code, nothing important is missing, and nothing is invented. The code is the source of truth; the README is the thing under test.

## 1. Apply the explicit fixes first

If the user named concrete changes (a default value, a wording), make them exactly as asked. Look for the same stale fact elsewhere — docstrings, comments, other docs — and fix those too, since they usually drifted together. Mention them in the report.

Values the user gives that aren't in the repo (e.g. "prod is 25", because prod config lives in infra or a parameter store) are written as the user stated them, e.g. `Default 24 (prod: 25)`. Don't try to verify them.

## 2. Collect the code facts

Read the README fully, then collect facts from the code. Read files; don't rely on memory or on the README itself.

| README topic | Where the truth is |
|---|---|
| Env vars and defaults | the settings code (pydantic `BaseSettings`, `os.environ`/`getenv`, `process.env`, a config struct): name, prefix, default, whether it's used at all (grep each field) |
| What the service does, inputs/outputs | entry point (`app.py`, a Lambda `handler`, `__main__`, `main.go`, `index.ts`), message routing / API routes, publishers (queues, topics, HTTP clients) |
| Background jobs | task runner / scheduler registration |
| Ports, health checks | server setup; for a library default, check the version pinned in the lock file |
| Local dev, tests, build | `Makefile`, `pyproject.toml` / `package.json` / `go.mod` (language version, tooling), `docker-compose`/`*_local.yml`, `Dockerfile` |
| CI / deploy | `.github/workflows/`, `bitbucket-pipelines.yml`, `.gitlab-ci.yml`, `buildspec.yml`, IaC (CDK, Terraform) |

## 3. Diff and classify

For each README statement, decide which it is:
- **Wrong**: the value or behavior differs from the code. Fix it to match the code.
- **Stale**: it refers to something removed or no longer used. Remove it, or mark it `**NOT USED**` / `**DEPRECATED**` if the setting still exists in code.
- **Ambiguous**: e.g. example values that read like defaults. Rewrite them so they are unambiguous (state the real code defaults).
- **Missing**: env vars, pipelines, jobs, endpoints or commands that exist in code but not in the README. Add them briefly.

Keep the README's existing structure, tone and formatting. Add a new section only for a clearly missing topic (usually "Local development").

Leave a section alone, and say so in the report, if you didn't actually verify it. This applies especially to long, recently written sections such as CI docs.

## 4. Ask when in doubt

Ask the user (AskUserQuestion, batched) instead of guessing when:
- the correct value is environment-specific and not in the repo;
- it's unclear whether something is intentionally kept (a deprecated flag still set in prod?);
- a fix means deleting a whole section.

For small uncertainties, make the conservative edit and list it under "check please" in the report.

## 5. Guardrails

- Never write secret values into the README, and never write a command that reads or prints a secret or key file (e.g. `$(cat ~/.ssh/id_rsa)`). Use a placeholder instead: `--build-arg deploy_key=...`.
- If you notice a secret committed in the repo while auditing (a password in a buildspec, say), don't copy it anywhere. Flag it in the report as a separate issue.
- Don't commit. Leave the changes for the user.
- If `CLAUDE.md` repeats a fact you corrected, fix it there as well.

## 6. Report

Reply in the user's language, grouped like this:
- **What was asked:** the explicit fixes, including the extra places where the same stale fact was found.
- **Inaccuracies:** `README said X, code says Y (file:line)`.
- **Added:** the missing items.
- **Check please:** unverified sections, values taken on the user's word, open questions, and side findings such as committed secrets.
