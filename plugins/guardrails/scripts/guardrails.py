#!/usr/bin/env python3
"""PreToolUse hook for the Bash tool: codex-guard, destructive-guard, deploy-guard.

Contract (Claude Code hooks):
- input: the hook event as JSON on stdin (`tool_name`, `tool_input.command`, `cwd`);
- nothing to say: exit 0, no output;
- ask or deny: exit 0 with
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "ask" | "deny",
                          "permissionDecisionReason": "..."}}

A crash in a hook does not block the tool call in Claude Code, so every internal error
is turned into "ask": a broken guard asks the human instead of silently allowing.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from guards import codex, deploy, destructive  # noqa: E402
from guards.common import ALLOW, ASK, Finding, guard_off, load_config, strongest  # noqa: E402
from guards.shell import parse  # noqa: E402

GUARDS = (("codex-guard", codex.check), ("destructive-guard", destructive.check), ("deploy-guard", deploy.check))


def decide(event: dict, env: dict[str, str]) -> tuple[str, str]:
    if event.get("tool_name", "Bash") != "Bash":
        return ALLOW, ""
    command = (event.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return ALLOW, ""
    cwd = event.get("cwd") or os.getcwd()
    parsed = parse(command, cwd=cwd, env=env)
    cfg = load_config(cwd, env)
    findings: list[Finding] = []
    for name, check in GUARDS:
        if guard_off(name.split("-")[0], env) or guard_off(name, env):
            continue
        findings += check(parsed.commands, env, cfg)
    active = [n for n, _ in GUARDS if not (guard_off(n.split("-")[0], env) or guard_off(n, env))]
    if parsed.opaque and active:
        findings.append(Finding(ASK, "guardrails", "cannot read this command fully: " + "; ".join(sorted(set(parsed.opaque)))))
    decision = strongest(findings)
    if decision == ALLOW:
        return ALLOW, ""
    lines = [f"[{f.guard}] {f.message}" for f in findings if f.decision == decision]
    return decision, "\n".join(lines)


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
        decision, reason = decide(event, dict(os.environ))
    except Exception as e:  # noqa: BLE001 - see module docstring
        decision = ASK
        reason = f"[guardrails] internal error, asking instead of allowing: {e!r}\n" + traceback.format_exc(limit=3)
    if decision == ALLOW:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
