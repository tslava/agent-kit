#!/usr/bin/env python3
"""Idempotently add a dependency cooldown to Poetry or uv projects.

Usage:
    python apply_cooldown.py [--days N] [--tool auto|poetry|uv] [PATH ...]

Poetry: `[solver] min-release-age = N` in poetry.toml.
uv:     `[tool.uv] exclude-newer = "N days"` in pyproject.toml.

Per repo:
- file or section missing -> add it (other content is preserved)
- key already set         -> leave as-is; report if the value differs
- tool not detected       -> report `unknown`, change nothing
"""
import argparse
import os
import re
import sys

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def _read(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _get(text, table, key):
    """Return table.key from TOML text, or None. `table` is a dotted path."""
    if text is None:
        return None
    if tomllib is not None:
        try:
            node = tomllib.loads(text)
            for part in table.split("."):
                node = node.get(part, {})
            return node.get(key)
        except Exception:
            pass  # fall back to regex on malformed TOML
    m = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$", text, re.MULTILINE)
    return m.group(1).strip('"\'') if m else None


def _ensure(path, table, key, value_toml):
    """Make sure [table] has key = value_toml. Returns (action, existing)."""
    text = _read(path)
    if text is None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"[{table}]\n{key} = {value_toml}\n")
        return "created", None

    existing = _get(text, table, key)
    if existing is not None:
        return "already-set", existing

    header = re.compile(rf"(^\s*\[{re.escape(table)}\][^\n]*\n)", re.MULTILINE)
    if header.search(text):
        new = header.sub(lambda m: f"{m.group(1)}{key} = {value_toml}\n", text, count=1)
    else:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new = f"{text}{sep}\n[{table}]\n{key} = {value_toml}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return "updated", None


def detect(repo):
    pyproject = _read(os.path.join(repo, "pyproject.toml")) or ""
    if os.path.exists(os.path.join(repo, "uv.lock")) or re.search(r"^\s*\[tool\.uv\]", pyproject, re.M):
        return "uv"
    if os.path.exists(os.path.join(repo, "poetry.lock")) or re.search(r"^\s*\[tool\.poetry\]", pyproject, re.M):
        return "poetry"
    return None


def apply(repo, days, tool):
    tool = detect(repo) if tool == "auto" else tool
    if tool == "poetry":
        target = os.path.join(repo, "poetry.toml")
        action, existing = _ensure(target, "solver", "min-release-age", str(days))
        wanted = str(days)
    elif tool == "uv":
        target = os.path.join(repo, "pyproject.toml")
        if not os.path.exists(target):
            return "unknown", target, "no pyproject.toml"
        action, existing = _ensure(target, "tool.uv", "exclude-newer", f'"{days} days"')
        wanted = f"{days} days"
    else:
        return "unknown", repo, "neither Poetry nor uv detected; pass --tool"
    note = ""
    if existing is not None and str(existing) != wanted:
        note = f"value={existing}, wanted {wanted}; left as-is"
    return action, target, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=15, help="cooldown in days (default: 15)")
    ap.add_argument("--tool", choices=["auto", "poetry", "uv"], default="auto")
    ap.add_argument("paths", nargs="*", default=["."], help="repo directories")
    args = ap.parse_args()

    rc = 0
    for repo in args.paths:
        try:
            action, target, note = apply(repo, args.days, args.tool)
            print(f"{action:12} {target}" + (f"  ({note})" if note else ""))
            if action == "unknown":
                rc = 1
        except Exception as e:  # pragma: no cover
            print(f"{'ERROR':12} {repo}: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
