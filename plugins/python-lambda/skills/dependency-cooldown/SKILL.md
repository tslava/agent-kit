---
name: dependency-cooldown
description: Add or check a supply-chain "cooldown" so the Python resolver ignores package versions published in the last N days (default 15). Handles Poetry (`[solver] min-release-age` in poetry.toml) and uv (`[tool.uv] exclude-newer` in pyproject.toml). Use whenever the user wants a release-age rule, a dependency cooldown, protection against freshly published malicious packages, or asks to "add the min release age rule" / "set exclude-newer" — in one repo or across many — even if they don't name the config file.
---

# Dependency cooldown

A cooldown makes the resolver ignore any release younger than N days. Malicious
releases (typosquats, hijacked maintainer accounts) are often found and yanked soon after
publication, so a delay reduces your exposure to brand-new releases, at the cost of
getting fixes a little later. Default here: **15 days**.

The setting has a different name and a different file per tool:

| Tool | File | Setting |
|---|---|---|
| Poetry | `poetry.toml` (repo root, *not* `pyproject.toml`) | `[solver]` → `min-release-age = 15` |
| uv | `pyproject.toml` | `[tool.uv]` → `exclude-newer = "15 days"` |

## How to apply it

Use the bundled script. It detects the tool per repo, is idempotent, and never overwrites
a value that is already set:

```bash
python <skill-dir>/scripts/apply_cooldown.py [--days 15] [--tool auto|poetry|uv] [PATH ...]
```

- `PATH` is a repo directory. Defaults to the current directory. Pass several for a batch.
- `--tool auto` (default): `uv.lock` or `[tool.uv]` → uv; `poetry.lock` or `[tool.poetry]` → Poetry;
  neither → the script reports `unknown` and changes nothing. Ask the user which tool they use.
- Output is one line per repo: `created`, `updated`, `already-set`, `already-set (value=…)`,
  or `unknown`.

If a repo already has a **different** value, the script leaves it alone and reports it.
Surface that to the user instead of overriding it: someone chose that number.

## What it produces

Poetry, `poetry.toml` (existing sections such as `[virtualenvs]` are preserved):
```toml
[solver]
min-release-age = 15
```

uv, `pyproject.toml`:
```toml
[tool.uv]
exclude-newer = "15 days"
```

## Notes

- The setting affects the **next** `poetry lock` / `uv lock`. It does not rewrite the
  existing lockfile. Say so if the user expects dependency changes right away.
- An urgent security fix younger than the cooldown will be ignored by the resolver. The
  escape hatch is a one-off explicit pin for that package, with a comment and a date to
  remove it — not lowering the cooldown for everything.
- Combine with "use the latest version" rules carefully: "latest" means "latest release
  older than the cooldown".
- Committing is out of scope: report what changed and let the user commit.
