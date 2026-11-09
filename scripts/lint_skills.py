#!/usr/bin/env python3
"""Lint every plugin and skill in this marketplace. Stdlib only.

Checks:
- marketplace.json and each plugin.json parse, and every listed plugin source exists;
- every skill dir has SKILL.md with YAML frontmatter holding `name` and `description`;
- `name` matches the directory, is kebab-case, <= 64 chars;
- `description` is 1..1024 chars;
- every relative link or `references/...` / `scripts/...` path mentioned in a skill exists;
- no absolute home paths, no 12-digit numbers (AWS account ids), no non-example emails.
Exit 1 on any error.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {msg}")


def frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    key = None
    for line in text[4:end].splitlines():
        m = re.match(r"^([a-zA-Z][\w-]*):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            fields[key] = "" if value in (">", ">-", "|", "|-") else value
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields


def check_skill(skill_dir: Path) -> None:
    md = skill_dir / "SKILL.md"
    if not md.exists():
        err(skill_dir, "missing SKILL.md")
        return
    text = md.read_text(encoding="utf-8")
    fm = frontmatter(text)
    if fm is None:
        err(md, "missing or unterminated YAML frontmatter")
        return
    name, desc = fm.get("name", ""), fm.get("description", "")
    if name != skill_dir.name:
        err(md, f"name {name!r} != directory {skill_dir.name!r}")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
        err(md, f"name {name!r} must be kebab-case, <= 64 chars")
    if not 1 <= len(desc) <= 1024:
        err(md, f"description length {len(desc)} not in 1..1024")
    for path in skill_dir.rglob("*.md"):
        body = path.read_text(encoding="utf-8")
        refs = set(re.findall(r"\]\(((?!https?://|#|mailto:)[^)\s]+)\)", body))
        refs |= set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", body))
        for ref in refs:
            target = (skill_dir / ref) if ref.startswith(("references/", "scripts/")) else (path.parent / ref)
            if not target.exists():
                err(path, f"broken reference {ref!r}")


def check_hygiene(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"/(Users|home)/[a-z]", line):
            err(path, f"line {i}: absolute home path")
        if re.search(r"(?<![\d.])\d{12}(?![\d.])", line):
            err(path, f"line {i}: 12-digit number (AWS account id?)")
        for email in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", line):
            if not email.split("@")[1].endswith(("example.com", "example.org")):
                err(path, f"line {i}: non-example email {email}")


def main() -> int:
    market = ROOT / ".claude-plugin" / "marketplace.json"
    data = json.loads(market.read_text())
    for plugin in data.get("plugins", []):
        src = (ROOT / plugin["source"]).resolve()
        manifest = src / ".claude-plugin" / "plugin.json"
        if not manifest.exists():
            err(market, f"plugin {plugin['name']!r}: no {manifest.relative_to(ROOT)}")
            continue
        pj = json.loads(manifest.read_text())
        if pj.get("name") != plugin["name"]:
            err(manifest, f"name {pj.get('name')!r} != marketplace entry {plugin['name']!r}")
        skills = src / "skills"
        for skill_dir in sorted(p for p in skills.iterdir() if p.is_dir()) if skills.exists() else []:
            check_skill(skill_dir)
    skip = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "cdk.out", "out"}
    for path in ROOT.rglob("*"):
        if path.is_file() and not skip & set(path.parts) and path.suffix in {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt"}:
            check_hygiene(path)
    for path in ROOT.rglob("*"):
        if path.is_file() and not skip & set(path.parts) and path.suffix in {".zip", ".pyc", ".whl", ".so", ".db", ".sqlite"}:
            err(path, "build artifact or binary file must not be committed")
    for e in errors:
        print(e)
    print(f"{len(errors)} error(s)", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
