"""codex-guard: `codex exec` only runs read-only, without approval prompts, without GUI tools, with stdin closed.

Why each control is required:
- `-s read-only` (or `-c sandbox_mode="read-only"` for `exec resume`): Codex reviews, it does not edit.
- `-c approval_policy="never"`: settings in ~/.codex/config.toml (for example a directory with
  `trust_level = "untrusted"`) can turn approvals on. In exec mode every shell command is then
  rejected, and the model looks for another way to act.
- `-c features.plugins=false`: bundled Codex plugins bring GUI tools (computer use, a REPL that
  can click and type into other apps). With shell commands rejected, a model used one of them to
  type into the user's terminals.
- `< /dev/null` (or any stdin redirect or pipe): `codex exec` reads stdin even when a prompt is
  given, so an open stdin makes a background run hang.
- extra MCP servers listed in config (`codex_guard.disable_mcp`) must be switched off with
  `-c mcp_servers.<name>.enabled=false`. Only list servers that exist: Codex refuses to start
  when that override names a server it does not know.

The guard only sees `codex` when it is called directly in the Bash command. A wrapper script
that calls codex is not inspected; harden the wrapper itself.
"""
from __future__ import annotations

import shlex

from .common import DENY, Finding, ask_requested, ASK
from .shell import Simple, Word

NAME = "codex-guard"
_WITH_VALUE = {"-c", "--config", "--enable", "--disable", "-i", "--image", "-m", "--model", "--local-provider",
               "-p", "--profile", "-s", "--sandbox", "-a", "--ask-for-approval", "-C", "--cd", "--add-dir",
               "--thread-source", "--cyber-access-program", "--output-schema", "--color", "-o",
               "--output-last-message"}
_DANGEROUS = {"--dangerously-bypass-approvals-and-sandbox", "--yolo", "--full-auto", "--approve-for-me"}


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _scan(argv: list[Word]) -> tuple[list[str], dict[str, list[str]], list[str], set[str]]:
    """(positionals, option values in order, config overrides 'k=v' in order, flags)."""
    positionals, values, overrides, flags = [], {}, [], set()
    i = 1
    while i < len(argv):
        t = argv[i].text
        key, eq, inline = t.partition("=")
        if t.startswith("--") and eq and key in _WITH_VALUE:
            values.setdefault(key, []).append(inline)
            if key == "--config":
                overrides.append(inline)
            i += 1
            continue
        if t in _WITH_VALUE:
            v = argv[i + 1].text if i + 1 < len(argv) else ""
            values.setdefault(t, []).append(v)
            if t in ("-c", "--config"):
                overrides.append(v)
            i += 2
            continue
        if t.startswith("-") and t != "-":
            flags.add(t)
        else:
            positionals.append(t)
        i += 1
    return positionals, values, overrides, flags


def _settings(overrides: list[str], key: str) -> list[str]:
    """Every value given for a config key, in order."""
    found = []
    for o in overrides:
        k, eq, v = o.partition("=")
        if eq and k.strip() == key:
            found.append(_unquote(v))
    return found


def _all_equal(values: list[str], wanted: str) -> bool:
    """Set at least once, and never to anything else: a later conflicting value cannot sneak in."""
    return bool(values) and all(v == wanted for v in values)


def check_one(cmd: Simple, disable_mcp: list[str]) -> Finding | None:
    positionals, values, overrides, flags = _scan(cmd.argv)
    if not positionals or positionals[0] not in ("exec", "e"):
        return None
    resume = len(positionals) > 1 and positionals[1] == "resume"
    missing: list[str] = []
    add: list[str] = []
    fixed: set[str] = set()

    bad_flags = sorted(flags & _DANGEROUS)
    if bad_flags:
        return Finding(DENY, NAME, f"`codex exec` with {', '.join(bad_flags)} turns off the sandbox or approvals. "
                                   "Run it read-only: -s read-only -c approval_policy='\"never\"'.")

    sandbox = values.get("-s", []) + values.get("--sandbox", []) + _settings(overrides, "sandbox_mode")
    if not _all_equal(sandbox, "read-only"):
        missing.append(f"read-only sandbox (now: {', '.join(sandbox) or 'not set'})")
        add += ["-c", "sandbox_mode=\"read-only\""] if resume else ["-s", "read-only"]
        fixed.add("sandbox")
    approval = values.get("-a", []) + values.get("--ask-for-approval", []) + _settings(overrides, "approval_policy")
    if not _all_equal(approval, "never"):
        missing.append(f"approval_policy never (now: {', '.join(approval) or 'not set'})")
        add += ["-c", "approval_policy=\"never\""]
        fixed.add("approval")
    plugins = (_settings(overrides, "features.plugins")
               + ["false" for v in values.get("--disable", []) if v == "plugins"]
               + ["true" for v in values.get("--enable", []) if v == "plugins"])
    if not _all_equal(plugins, "false"):
        missing.append("Codex plugins off (they bring the computer-use tools)")
        add += ["-c", "features.plugins=false"]
        fixed.add("plugins")
    for server in disable_mcp:
        if not _all_equal(_settings(overrides, f"mcp_servers.{server}.enabled"), "false"):
            missing.append(f"MCP server {server} off")
            add += ["-c", f"mcp_servers.{server}.enabled=false"]
            fixed.add(f"mcp:mcp_servers.{server}.enabled")
    stdin_add = ""
    if not cmd.stdin_redirected():
        missing.append("stdin closed (< /dev/null)")
        stdin_add = " < /dev/null"
    if not missing:
        return None

    redirects = "".join(f" {r.fd}{r.op} {shlex.quote(r.target.text)}" for r in cmd.redirects
                        if r.target is not None and r.target.known and r.op not in ("<<", "<<-"))
    suggestion = _suggest(cmd.argv, positionals, add, fixed) + redirects + stdin_add
    if cmd.stdin_from_pipe:
        suggestion = "<the same input> | " + suggestion
    msg = ("`codex exec` is missing: " + "; ".join(missing) + ".\nRun instead:\n  " + suggestion)
    return Finding(DENY, NAME, msg)


def _conflicting(texts: list[str], start: int, fixed: set[str]) -> set[int]:
    """Indexes of options that set a key the suggestion fixes, so the old value is dropped."""
    drop: set[int] = set()
    i = start
    while i < len(texts):
        t = texts[i]
        key, eq, inline = t.partition("=")
        if t in _WITH_VALUE or (t.startswith("--") and eq and key in _WITH_VALUE):
            opt, value, width = (t, texts[i + 1] if i + 1 < len(texts) else "", 2) if t in _WITH_VALUE \
                else (key, inline, 1)
            cfg_key = value.partition("=")[0].strip() if opt in ("-c", "--config") else ""
            hit = (("sandbox" in fixed and (opt in ("-s", "--sandbox") or cfg_key == "sandbox_mode"))
                   or ("approval" in fixed and (opt in ("-a", "--ask-for-approval") or cfg_key == "approval_policy"))
                   or ("plugins" in fixed and (cfg_key == "features.plugins"
                                               or (opt in ("--enable", "--disable") and value == "plugins")))
                   or (cfg_key.startswith("mcp_servers.") and f"mcp:{cfg_key}" in fixed))
            if hit:
                drop.update(range(i, i + width))
            i += width
            continue
        i += 1
    return drop


def _suggest(argv: list[Word], positionals: list[str], add: list[str], fixed: set[str]) -> str:
    if not all(w.known for w in argv):
        head = "codex exec" + (" resume <session-id>" if "resume" in positionals[:2] else "")
        return shlex.join(head.split()) + " " + shlex.join(add) + " \"<prompt>\""
    texts = [w.text for w in argv]
    # put the missing options right after `exec` (after `exec resume <id>` for a resume)
    idx = next(i for i, t in enumerate(texts) if t in ("exec", "e"))
    insert_at = idx + 1
    if "resume" in positionals[:2]:
        r = texts.index("resume", idx)
        insert_at = r + 1
        if r + 1 < len(texts) and not texts[r + 1].startswith("-"):
            insert_at = r + 2
    drop = _conflicting(texts, 1, fixed)
    head = [t for i, t in enumerate(texts[:insert_at]) if i not in drop]
    tail = [t for i, t in enumerate(texts[insert_at:], insert_at) if i not in drop]
    return shlex.join(head + add + tail)


def check(commands: list[Simple], env: dict[str, str], cfg: dict) -> list[Finding]:
    disable_mcp = list(cfg.get("codex_guard", {}).get("disable_mcp", []))
    findings = []
    for cmd in commands:
        if cmd.name != "codex":
            continue
        f = check_one(cmd, disable_mcp)
        if f is None:
            continue
        if f.decision == DENY and ask_requested(cmd):
            f = Finding(ASK, NAME, f.message + "\n(GUARDRAILS_ASK=1: asking the human instead of blocking)")
        findings.append(f)
    return findings
