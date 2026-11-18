"""destructive-guard: stop commands that delete or discard work that may not be recoverable.

Covered (deny): recursive `rm` outside temp dirs, `find -delete`, `find -exec rm`,
`git reset --hard`, `git clean -f`, `git checkout -- <paths>` / `git checkout .` /
`git checkout -f`, `git restore` of the working tree, `git push --force` / `-f` /
`+refspec` / `--mirror`.
Allowed on purpose: `git push --force-with-lease` (and `--force-if-includes` with it).
Ask: anything above whose target is only known at run time, remote branch deletes.
"""
from __future__ import annotations

import os
import tempfile

from .common import ALLOW, ASK, DENY, Finding, ask_requested, git_globals, show
from .shell import UNKNOWN, Simple, Word

NAME = "destructive-guard"
HINT = ("Delete files one by one with explicit paths, or ask the human to run it. "
        "If the human has agreed, prefix the command with GUARDRAILS_ASK=1 to get a confirmation prompt.")


_DELETERS = {"rm", "unlink", "shred", "rmdir"}


def _q(paths: list[str]) -> str:
    return ", ".join(f"`{p}`" for p in paths)


def _temp_roots(env: dict[str, str], extra: list[str], cwd: str | None) -> list[str]:
    roots = ["/tmp", "/private/tmp", "/var/tmp"]
    try:
        roots.append(tempfile.gettempdir())
    except OSError:
        pass  # no writable temp dir: the fixed roots still apply
    if env.get("TMPDIR"):
        roots.append(env["TMPDIR"])
    for r in extra:
        r = os.path.expanduser(r)
        if not os.path.isabs(r):
            if cwd is None:
                continue
            r = os.path.join(cwd, r)
        roots.append(r)
    return sorted({os.path.realpath(r) for r in roots})


def _inside(path: str, roots: list[str], allow_equal: bool = False) -> bool:
    for root in roots:
        if path == root:
            if allow_equal:
                return True
            continue
        if path.startswith(root.rstrip("/") + "/"):
            return True
    return False


def _check_path(w: Word, cwd: str | None, roots: list[str]) -> tuple[str, str]:
    """(decision, shown path) for one deletion target."""
    if not w.known:
        return ASK, w.text.replace("\x00", "$…")
    text = os.path.expanduser(w.text)
    if not os.path.isabs(text):
        if cwd is None:
            return ASK, text
        text = os.path.join(cwd, text)
    if w.glob:
        parent, last = os.path.split(text.rstrip("/"))
        if any(ch in parent for ch in "*?[") or last.startswith("."):
            return ASK, w.text
        real_parent = os.path.realpath(parent)
        return (ALLOW if _inside(real_parent, roots, allow_equal=True) else DENY), w.text
    real = os.path.realpath(text)
    return (ALLOW if _inside(real, roots) else DENY), w.text


def _rm(cmd: Simple, roots: list[str]) -> Finding | None:
    recursive, operands, opts_done, maybe_flags = False, [], False, False
    for w in cmd.argv[1:]:
        t = w.text
        if not opts_done and t == "--":
            opts_done = True
        elif not opts_done and t.startswith("--"):
            recursive |= t in ("--recursive", "--dir")
        elif not opts_done and t.startswith("-") and len(t) > 1 and w.known:
            recursive |= "r" in t or "R" in t
        else:
            if not opts_done and t.startswith(UNKNOWN):
                maybe_flags = True  # `rm $FLAGS data`: the value may be -rf
            operands.append(w)
    # with a run-time word that may hold flags, judge as recursive but never deny: ask
    unsure = maybe_flags and not recursive and len(operands) > 1
    if not (recursive or unsure):
        return None
    what = "recursive rm" if recursive else "rm with options known only at run time"
    if cmd.unknown_args:
        return Finding(ASK, NAME, f"{what} on paths known only at run time ({cmd.via}): {show(cmd.argv)}")
    worst, bad = ALLOW, []
    for w in operands:
        decision, shown = _check_path(w, cmd.cwd, roots)
        if decision != ALLOW:
            bad.append(shown)
            worst = DENY if DENY in (worst, decision) else ASK
    if worst == ALLOW:
        return None
    if worst == ASK:
        return Finding(ASK, NAME, f"{what}: cannot tell where these point before running: {_q(bad)}")
    if unsure:
        return Finding(ASK, NAME, f"{what}, may delete recursively outside temp dirs: {show(cmd.argv)}")
    return Finding(DENY, NAME, f"{what} outside temp dirs: {_q(bad)}. {HINT}")


def _find(cmd: Simple, roots: list[str]) -> Finding | None:
    argv = cmd.argv
    i = 1
    while i < len(argv) and argv[i].text in ("-H", "-L", "-P"):
        i += 1
    starts = []
    while i < len(argv) and not argv[i].text.startswith(("-", "(", "!")):
        starts.append(argv[i])
        i += 1
    rest = [w.text for w in argv[i:]]
    action = "-delete" if "-delete" in rest else None
    for j, t in enumerate(rest[:-1]):
        if t in ("-exec", "-execdir", "-ok", "-okdir") and rest[j + 1].rsplit("/", 1)[-1] in _DELETERS:
            action = f"{t} {rest[j + 1]}"
    if action is None:
        return None
    worst, bad = ALLOW, []
    for w in starts or [Word(".")]:
        decision, shown = _check_path(w, cmd.cwd, roots)
        if decision != ALLOW:
            bad.append(shown)
            worst = DENY if DENY in (worst, decision) else ASK
    if worst == ALLOW:
        return None
    if worst == ASK:
        return Finding(ASK, NAME, f"find {action}: cannot tell where these point: {_q(bad)}")
    return Finding(DENY, NAME, f"find {action} outside temp dirs: {_q(bad)}. {HINT}")


def _git(cmd: Simple) -> Finding | None:
    _, i = git_globals(cmd)
    if i >= len(cmd.argv):
        return None
    sub = cmd.argv[i]
    args = cmd.argv[i + 1:]
    texts = [w.text for w in args]
    if not sub.known:
        return Finding(ASK, NAME, f"git subcommand known only at run time: {show(cmd.argv)}")
    s = sub.text
    shown = show(cmd.argv)

    def short(letter: str) -> bool:
        return any(t.startswith("-") and not t.startswith("--") and letter in t[1:] for t in texts)

    if s in ("reset", "clean") and any(not w.known for w in args):
        return Finding(ASK, NAME, f"`{shown}`: arguments known only at run time")
    if s == "reset" and "--hard" in texts:
        return Finding(DENY, NAME, f"`{shown}` throws away uncommitted changes. "
                                   "Use `git stash` first, or ask the human.")
    if s == "clean" and ("--force" in texts or short("f")) and not ("--dry-run" in texts or short("n")):
        return Finding(DENY, NAME, f"`{shown}` deletes untracked files. Run `git clean -n` to list them "
                                   "and ask the human.")
    if s == "checkout":
        if "--force" in texts or "-f" in texts:
            return Finding(DENY, NAME, f"`{shown}` throws away local changes. Ask the human.")
        if "--" in texts and texts.index("--") < len(texts) - 1:
            return Finding(DENY, NAME, f"`{shown}` overwrites local changes in those files. Ask the human, "
                                       "or `git stash` first.")
        if "." in texts or ":/" in texts:
            return Finding(DENY, NAME, f"`{shown}` throws away all local changes. Ask the human.")
    if s == "restore":
        staged = "--staged" in texts or short("S")
        worktree = "--worktree" in texts or short("W")
        paths = [t for t in texts if not t.startswith("-")]
        if paths and (worktree or not staged):
            return Finding(DENY, NAME, f"`{shown}` overwrites local changes in those files. Ask the human, "
                                       "or `git stash` first.")
    if s == "push":
        return _push(cmd, args, shown)
    return None


def _push(cmd: Simple, args: list[Word], shown: str) -> Finding | None:
    with_value = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
    force = mirror = delete = has_repo = runtime = False
    positionals: list[Word] = []
    i = 0
    while i < len(args):
        t = args[i].text
        if not args[i].known:
            runtime = True
        if t in with_value:
            has_repo |= t == "--repo"
            i += 2
            continue
        if t.startswith("--repo="):
            has_repo = True
        elif t == "--force" or (t.startswith("-") and not t.startswith("--") and "f" in t[1:]):
            force = True
        elif t == "--mirror":
            mirror = True
        elif t in ("--delete", "-d") or (t.startswith("-") and not t.startswith("--") and "d" in t[1:]):
            delete = True
        elif not t.startswith("-"):
            positionals.append(args[i])
        i += 1
    refspecs = positionals if has_repo else positionals[1:]
    plus = [w.text for w in refspecs if w.text.startswith("+")]
    if force or mirror or plus:
        how = "--mirror" if mirror else ("+refspec " + ", ".join(plus) if plus else "--force")
        return Finding(DENY, NAME, f"`{shown}` force-pushes ({how}) and can drop commits on the remote. "
                                   "Use `git push --force-with-lease` without `+` if the rewrite is intended.")
    if delete or any(w.text.startswith(":") for w in refspecs):
        return Finding(ASK, NAME, f"`{shown}` deletes a remote branch.")
    if runtime:
        return Finding(ASK, NAME, f"`{shown}`: an option or refspec is known only at run time (it could force-push).")
    return None


def check(commands: list[Simple], env: dict[str, str], cfg: dict) -> list[Finding]:
    gcfg = cfg.get("destructive_guard", {})
    findings: list[Finding] = []
    for cmd in commands:
        name = cmd.name
        if name is None:
            findings.append(Finding(ASK, NAME, f"program name known only at run time: {show(cmd.argv)}"))
            continue
        roots = _temp_roots(env, gcfg.get("extra_safe_roots", []), cmd.cwd)
        f = None
        if name in _DELETERS and cmd.via == "find -exec":
            continue  # judged with its find command
        if name == "rm":
            f = _rm(cmd, roots)
        elif name == "find":
            f = _find(cmd, roots)
        elif name == "git":
            f = _git(cmd)
        if f is None:
            continue
        if f.decision == DENY and ask_requested(cmd):
            f = Finding(ASK, NAME, f.message + " (GUARDRAILS_ASK=1: asking the human instead of blocking)")
        findings.append(f)
    return findings
