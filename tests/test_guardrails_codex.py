"""codex-guard: `codex exec` must run read-only, with approvals off, plugins off and stdin closed."""
import pytest

import guardrails

ENV = {"HOME": "/srv/agent-home", "GUARDRAILS_CONFIG": "/nonexistent.json"}
SAFE = "-s read-only -c approval_policy='\"never\"' -c features.plugins=false"


def decide(cmd, env=ENV):
    return guardrails.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/srv/project"}, dict(env))


ALLOW = [
    f"codex exec {SAFE} 'review the diff' < /dev/null",
    f"codex exec -m gpt-6-luna -c model_reasoning_effort=high {SAFE} --skip-git-repo-check 'x' < /dev/null > out.log 2>&1",
    f"$HOME/.local/bin/codex exec {SAFE} 'x' < /dev/null",
    "codex exec --sandbox=read-only -c approval_policy=never --disable plugins 'x' < /dev/null",
    f"codex exec {SAFE} - < prompt.md",
    f"cat prompt.md | codex exec {SAFE} -",
    f"codex exec {SAFE} 'x' <<< ''",
    "codex exec resume 0199a-id -c sandbox_mode='\"read-only\"' -c approval_policy='\"never\"' "
    "-c features.plugins=false 'reply' < /dev/null",
    "codex --version",
    "codex mcp list --json",
    "echo 'codex exec without flags'",
]

DENY = [
    "codex exec 'review'",
    "codex exec -s read-only 'x' < /dev/null",
    "codex exec -s workspace-write -c approval_policy=never -c features.plugins=false 'x' < /dev/null",
    "codex exec -c approval_policy=never -c features.plugins=false 'x' < /dev/null",
    "codex exec -s read-only -c features.plugins=false 'x' < /dev/null",
    "codex exec -s read-only -c approval_policy=never 'x' < /dev/null",
    f"codex exec {SAFE} 'x'",
    f"codex exec {SAFE} 'x' > out.log 2>&1 &",
    "codex exec --dangerously-bypass-approvals-and-sandbox 'x' < /dev/null",
    f"codex exec {SAFE} --full-auto 'x' < /dev/null",
    "codex e 'x'",
    "codex exec resume 0199a-id 'reply' < /dev/null",
    "bash -c \"codex exec 'x'\"",
    "cd repo && codex exec -s read-only 'x' < /dev/null",
    "codex exec -p review 'x' < /dev/null",
    "codex exec -s read-only -c approval_policy=never --disable plugins --enable plugins 'x' < /dev/null",
    "codex exec -s read-only -c approval_policy=never -c features.plugins=false -c features.plugins=true 'x' < /dev/null",
    "codex exec -s read-only -c sandbox_mode=workspace-write -c approval_policy=never -c features.plugins=false 'x' < /dev/null",
    "codex exec -s read-only -c approval_policy=never -c approval_policy=on-request -c features.plugins=false 'x' < /dev/null",
]


@pytest.mark.parametrize("cmd", ALLOW)
def test_allowed(cmd):
    assert decide(cmd) == ("allow", "")


@pytest.mark.parametrize("cmd", DENY)
def test_denied(cmd):
    decision, reason = decide(cmd)
    assert decision == "deny", reason
    assert "codex-guard" in reason


@pytest.mark.parametrize("cmd", [c for c in DENY if "dangerously" not in c and "full-auto" not in c
                                 and "workspace-write" not in c and "bash -c" not in c and "cd repo" not in c])
def test_suggested_command_passes_the_guard(cmd):
    _, reason = decide(cmd)
    suggestion = reason.split("Run instead:\n", 1)[1].strip()
    assert decide(suggestion) == ("allow", ""), suggestion


def test_reason_names_every_missing_control():
    _, reason = decide("codex exec 'x'")
    for part in ("read-only sandbox", "approval_policy never", "plugins off", "stdin closed"):
        assert part in reason


def test_resume_gets_sandbox_via_config_not_flag():
    _, reason = decide("codex exec resume 0199a-id 'reply' < /dev/null")
    assert "sandbox_mode=" in reason and " -s " not in reason.split("Run instead:")[1]


def test_extra_mcp_servers_from_config(tmp_path):
    cfg = tmp_path / "guardrails.json"
    cfg.write_text('{"codex_guard": {"disable_mcp": ["node_repl"]}}')
    env = {**ENV, "GUARDRAILS_CONFIG": str(cfg)}
    decision, reason = decide(f"codex exec {SAFE} 'x' < /dev/null", env)
    assert decision == "deny" and "mcp_servers.node_repl.enabled=false" in reason
    ok = f"codex exec {SAFE} -c mcp_servers.node_repl.enabled=false 'x' < /dev/null"
    assert decide(ok, env)[0] == "allow"


def test_wrapper_scripts_are_not_seen():
    # documented limit: harden the wrapper itself (see run-codex.sh in the planning plugin)
    assert decide("bash plugins/planning/skills/exec/scripts/run-codex.sh 'x'")[0] == "allow"


def test_ask_prefix():
    assert decide("GUARDRAILS_ASK=1 codex exec 'x'")[0] == "ask"


def test_piped_suggestion_keeps_the_pipe():
    _, reason = decide("echo prompt | codex exec 'review'")
    suggestion = reason.split("Run instead:\n", 1)[1].strip()
    assert suggestion.startswith("<the same input> | ")
    assert "< /dev/null" not in suggestion  # stdin comes from the pipe
    assert decide(suggestion.replace("<the same input>", "echo prompt")) == ("allow", "")
