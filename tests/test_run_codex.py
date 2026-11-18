"""run-codex.sh (planning plugin) passes the safety controls, and its command passes codex-guard."""
import os
import shlex
import subprocess
from pathlib import Path

import pytest

import guardrails

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins/planning/skills/exec/scripts/run-codex.sh"


@pytest.fixture
def fake_codex(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text('#!/bin/bash\nfor a in "$@"; do printf "%s\\n" "$a"; done\n[ -t 0 ] && echo STDIN_TTY || echo STDIN_CLOSED\n')
    fake.chmod(0o755)
    return bin_dir


def run(fake_codex, **env):
    full = {"PATH": f"{fake_codex}:{os.environ['PATH']}", "HOME": os.environ.get("HOME", "/tmp"), **env}
    out = subprocess.run(["bash", str(SCRIPT), "review this"], cwd=ROOT, env=full, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    return out[:-1], out[-1]


def test_safety_controls_are_passed(fake_codex):
    args, stdin = run(fake_codex)
    joined = " ".join(args)
    assert "--sandbox read-only" in joined
    assert '-c approval_policy="never"' in joined
    assert "-c features.plugins=false" in joined
    assert stdin == "STDIN_CLOSED"


def test_safety_controls_survive_no_overrides(fake_codex):
    args, _ = run(fake_codex, CODEX_NO_OVERRIDES="1")
    assert '-c approval_policy="never"' in " ".join(args)
    assert not any(a.startswith("model_reasoning_effort") for a in args)


def test_extra_mcp_servers(fake_codex):
    args, _ = run(fake_codex, CODEX_DISABLE_MCP="node_repl browser")
    joined = " ".join(args)
    assert "mcp_servers.node_repl.enabled=false" in joined and "mcp_servers.browser.enabled=false" in joined


def test_the_wrapper_command_passes_codex_guard(fake_codex):
    args, _ = run(fake_codex)
    command = shlex.join(["codex", *args]) + " < /dev/null"
    decision, reason = guardrails.decide({"tool_name": "Bash", "tool_input": {"command": command},
                                          "cwd": "/srv/project"}, {"GUARDRAILS_CONFIG": "/nonexistent.json"})
    assert decision == "allow", reason
