"""The hook as Claude Code runs it: a subprocess, the event JSON on stdin, the decision on stdout."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "plugins/guardrails/scripts/guardrails.py"


def run(stdin: str, **env):
    full_env = {"PATH": os.environ.get("PATH", ""), "HOME": "/srv/agent-home", "GUARDRAILS_CONFIG": "/nonexistent.json",
                **env}
    p = subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=full_env,
                       timeout=30)
    return p.returncode, p.stdout, p.stderr


def event(command, tool="Bash"):
    return json.dumps({"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": {"command": command}, "cwd": "/srv/project"})


def decision(stdout):
    out = json.loads(stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    return out["permissionDecision"], out["permissionDecisionReason"]


def test_allow_prints_nothing():
    assert run(event("ls -la")) == (0, "", "")


def test_deny_is_json_on_stdout_with_exit_0():
    code, out, _ = run(event("git reset --hard"))
    assert code == 0
    d, reason = decision(out)
    assert d == "deny" and "git stash" in reason


def test_ask_for_opaque_command():
    code, out, _ = run(event('eval "$X"'))
    assert code == 0 and decision(out)[0] == "ask"


@pytest.mark.parametrize("stdin", ["", "not json", "[]"])
def test_bad_input_asks_or_passes_but_never_crashes(stdin):
    code, out, _ = run(stdin)
    assert code == 0
    if out:
        assert decision(out)[0] == "ask"


def test_other_tools_are_ignored():
    assert run(event("rm -rf /", tool="Write")) == (0, "", "")


def test_broken_config_asks_instead_of_allowing(tmp_path):
    bad = tmp_path / "guardrails.json"
    bad.write_text("{not json")
    code, out, _ = run(event("ls"), GUARDRAILS_CONFIG=str(bad))
    assert code == 0
    d, reason = decision(out)
    assert d == "ask" and "internal error" in reason


def test_switched_off_by_environment():
    assert run(event("git reset --hard"), GUARDRAILS_OFF="all") == (0, "", "")


def test_hooks_json_points_at_the_script():
    hooks = json.loads((ROOT / "plugins/guardrails/hooks/hooks.json").read_text())
    entry = hooks["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash"
    assert "scripts/guardrails.py" in entry["hooks"][0]["command"]
