"""Shared types and helpers for the guards."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .shell import Simple, Word

ALLOW, ASK, DENY = "allow", "ask", "deny"
_RANK = {ALLOW: 0, ASK: 1, DENY: 2}

# Prefix a command with this to turn a deny into a question to the human.
# The agent can type it too, so it never allows anything silently.
ASK_PREFIX = "GUARDRAILS_ASK"
# Set in the environment Claude Code starts with (the agent cannot change it):
# a comma list of guards to switch off, or "all".
OFF_ENV = "GUARDRAILS_OFF"


@dataclass
class Finding:
    decision: str
    guard: str
    message: str


def strongest(findings: list[Finding]) -> str:
    return max((f.decision for f in findings), key=_RANK.__getitem__, default=ALLOW)


def guard_off(name: str, env: dict[str, str]) -> bool:
    value = env.get(OFF_ENV, "")
    parts = {p.strip() for p in value.split(",") if p.strip()}
    return "all" in parts or name in parts


def ask_requested(cmd: Simple) -> bool:
    w = cmd.assigns.get(ASK_PREFIX)
    return w is not None and w.text == "1"


def run_git(cwd: str, *args: str, timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, p.stdout.strip()


def git_globals(cmd: Simple) -> tuple[str | None, int]:
    """For a `git` command: (cwd after -C options, index of the subcommand). cwd None = unknown."""
    argv, cwd, i = cmd.argv, cmd.cwd, 1
    with_value = {"-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env", "--super-prefix"}
    while i < len(argv):
        t = argv[i].text
        if t == "-C" and i + 1 < len(argv):
            target = argv[i + 1]
            if cwd is None or not target.known:
                cwd = None
            else:
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target.text)))
            i += 2
        elif t in with_value:
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            break
    return cwd, i


def load_config(cwd: str | None, env: dict[str, str]) -> dict:
    """User config (~/.claude/guardrails.json), then the project's .claude/guardrails.json on top."""
    cfg: dict = {}
    home = env.get("HOME", "")
    paths = [Path(env["GUARDRAILS_CONFIG"])] if env.get("GUARDRAILS_CONFIG") else [Path(home) / ".claude/guardrails.json"]
    if cwd:
        rc, top = run_git(cwd, "rev-parse", "--show-toplevel")
        if rc == 0 and top:
            paths.append(Path(top) / ".claude/guardrails.json")
    for p in paths:
        try:
            data = json.loads(p.read_text())
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as e:
            raise ValueError(f"cannot read {p}: {e}") from e
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key] = {**cfg[key], **value}
            else:
                cfg[key] = value
    return cfg


def show(words: list[Word]) -> str:
    return " ".join(w.text.replace("\x00", "$…") for w in words)
