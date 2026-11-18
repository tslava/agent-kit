"""deploy-guard: a push must not overwrite what is deployed on a shared environment.

Setting: several people push branches that deploy to the same shared environment (for
example a dev or staging stand). If my branch does not contain the commit that is deployed
there now, my push redeploys the stand without the other person's changes.

Rule: for every branch the push updates that matches `branches`, the commit deployed on
each watched environment must be an ancestor of the commit being pushed.

"Deployed commit" per environment: the newest deployment (by start time) that is in
progress or finished successfully. Failed and stopped deployments are skipped.

Provider: Bitbucket Cloud deployments. Config (in ~/.claude/guardrails.json or the
project's .claude/guardrails.json):

    "deploy_guard": {
      "provider": "bitbucket",
      "branches": "^(develop|feature/.+)$",
      "environment_type": "Staging",
      "token_env": "BITBUCKET_API_TOKEN",
      "user_env": "BITBUCKET_USER"
    }

Optional: "environments": [names] instead of environment_type; "fetch": false to skip the
`git fetch` before the check.

`user_env` set: Basic auth with that user (Atlassian API token). Not set: Bearer token
(repository or workspace access token).

When the state cannot be checked (no token, API error, timeout, the deployed commit is not
in local history, the source of the push cannot be resolved) the guard asks the human. It
never reports a push as safe without checking.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .common import ASK, DENY, Finding, ask_requested, git_globals, run_git, show
from .shell import Simple, Word

NAME = "deploy-guard"
API = "https://api.bitbucket.org/2.0/repositories"
HTTP_TIMEOUT = 10
MAX_PAGES = 4
_BB_URL = re.compile(r"bitbucket\.org[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$")


@dataclass
class Deployment:
    environment: str
    sha: str
    release: str
    state: str


HttpGet = Callable[[str, dict[str, str]], dict]


def http_get(url: str, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.load(r)


def bitbucket_deployed(workspace: str, repo: str, cfg: dict, env: dict[str, str], get: HttpGet) -> list[Deployment]:
    token = env.get(cfg.get("token_env", "BITBUCKET_API_TOKEN"), "")
    if not token:
        raise RuntimeError(f"no token in ${cfg.get('token_env', 'BITBUCKET_API_TOKEN')}")
    user = env.get(cfg["user_env"], "") if cfg.get("user_env") else ""
    if user:
        headers = {"Authorization": "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()}
    else:
        headers = {"Authorization": f"Bearer {token}"}
    base = f"{API}/{urllib.parse.quote(workspace)}/{urllib.parse.quote(repo)}"
    env_type = cfg.get("environment_type", "Staging")
    names = set(cfg.get("environments", []))
    result = []
    for e in _pages(get, f"{base}/environments/?pagelen=100", headers, MAX_PAGES):
        if names and e.get("name") not in names:
            continue
        if not names and e.get("environment_type", {}).get("name") != env_type:
            continue
        q = urllib.parse.urlencode({
            "environment": e["uuid"], "sort": "-state.started_on", "pagelen": 50,
            "fields": "next,values.state.name,values.state.status.name,values.release.commit.hash,values.release.name",
        })
        for d in _pages(get, f"{base}/deployments/?{q}", headers, MAX_PAGES):
            state = d.get("state", {})
            name = state.get("name", "")
            status = (state.get("status") or {}).get("name", "")
            if name == "IN_PROGRESS" or status == "SUCCESSFUL":
                result.append(Deployment(e.get("name", "?"), d["release"]["commit"]["hash"],
                                         d["release"].get("name", ""), "in progress" if name == "IN_PROGRESS" else "deployed"))
                break
        # all pages read and none successful: nothing is deployed there to protect.
        # Too many pages to read raises inside _pages, and the guard asks.
    return result


def _pages(get: HttpGet, url: str, headers: dict[str, str], max_pages: int):
    """Yield values from a paginated Bitbucket list, following `next`. Raises past max_pages."""
    for _ in range(max_pages):
        page = get(url, headers)
        yield from page.get("values", [])
        url = page.get("next")
        if not url:
            return
    raise RuntimeError(f"more than {max_pages} pages at {url.split('?')[0]}")


@dataclass
class PushTarget:
    src: str
    dst: str


def parse_push(cmd: Simple, cwd: str, args: list[Word]) -> tuple[str | None, list[PushTarget], str | None]:
    """(remote, targets, reason to ask). Deletes and tags are not targets."""
    with_value = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
    positionals: list[Word] = []
    repo_opt: str | None = None
    i = 0
    while i < len(args):
        t = args[i].text
        if t in with_value:
            if t == "--repo" and i + 1 < len(args):
                repo_opt = args[i + 1].text
            i += 2
            continue
        if t.startswith("--repo="):
            repo_opt = t.split("=", 1)[1]
        elif t in ("--all", "--branches", "--mirror"):
            return None, [], f"`git push {t}` updates many branches at once; not checked branch by branch"
        elif t in ("-n", "--dry-run"):
            return None, [], None
        elif t in ("-d", "--delete"):
            return None, [], None
        elif not t.startswith("-"):
            positionals.append(args[i])
        i += 1
    if any(not w.known for w in positionals):
        return None, [], "the remote or a refspec is known only at run time"
    if repo_opt is not None:
        remote, specs = repo_opt, [w.text for w in positionals]
    else:
        remote = positionals[0].text if positionals else None
        specs = [w.text for w in positionals[1:]]
    targets: list[PushTarget] = []
    if not specs:
        rc, cur = run_git(cwd, "symbolic-ref", "--short", "-q", "HEAD")
        if rc != 0 or not cur:
            return remote, [], "detached HEAD and no refspec: cannot tell which branch is pushed"
        rc, out = run_git(cwd, "for-each-ref", "--format=%(push:remotename)%00%(push:remoteref)%00%(push)",
                          f"refs/heads/{cur}")
        push_remote, push_ref, tracking = (out.split("\x00") + ["", "", ""])[:3]
        if remote is None:
            remote = push_remote or None
        if not push_ref and push_remote and tracking.startswith(f"refs/remotes/{push_remote}/"):
            push_ref = "refs/heads/" + tracking[len(f"refs/remotes/{push_remote}/"):]
        if not push_ref:
            # no upstream: with push.default=simple/current git pushes to the same name
            rc2, default = run_git(cwd, "config", "--get", "push.default")
            if default in ("", "simple", "current"):
                push_ref = f"refs/heads/{cur}"
            else:
                return remote, [], f"push.default={default} and no upstream: cannot tell the target branch"
        targets.append(PushTarget(cur, re.sub(r"^refs/heads/", "", push_ref)))
        return remote or "origin", targets, None
    for spec in specs:
        spec = spec.lstrip("+")
        src, colon, dst = spec.partition(":")
        if colon and not src:
            continue  # ":branch" deletes
        if src.startswith("refs/tags/") or dst.startswith("refs/tags/"):
            continue
        if not dst:
            if src == "HEAD":
                rc, cur = run_git(cwd, "symbolic-ref", "--short", "-q", "HEAD")
                if rc != 0:
                    return remote, [], "`git push <remote> HEAD` from a detached HEAD"
                dst = cur
            else:
                dst = src
        if dst == "HEAD":
            rc, cur = run_git(cwd, "symbolic-ref", "--short", "-q", "HEAD")
            dst = cur if rc == 0 else dst
        targets.append(PushTarget(src, re.sub(r"^refs/heads/", "", dst)))
    return remote or "origin", targets, None


def check_push(cmd: Simple, cfg: dict, env: dict[str, str], get: HttpGet) -> Finding | None:
    cwd, i = git_globals(cmd)
    if i >= len(cmd.argv) or cmd.argv[i].text != "push":
        return None
    shown = show(cmd.argv)
    if cwd is None:
        return Finding(ASK, NAME, f"`{shown}`: cannot tell which repository this runs in")
    remote, targets, reason = parse_push(cmd, cwd, cmd.argv[i + 1:])
    branches = re.compile(cfg.get("branches", r"^$"))
    if reason:
        return Finding(ASK, NAME, f"`{shown}`: {reason}")
    guarded = [t for t in targets if branches.search(t.dst)]
    if not guarded:
        return None
    if "://" in (remote or "") or "@" in (remote or ""):
        url = remote
        fetch_from = remote
    else:
        rc, url = run_git(cwd, "remote", "get-url", remote or "origin")
        if rc != 0:
            return Finding(ASK, NAME, f"`{shown}`: no remote {remote!r}")
        fetch_from = remote
    m = _BB_URL.search(url or "")
    if cfg.get("provider", "bitbucket") != "bitbucket" or not m:
        return None
    try:
        deployed = bitbucket_deployed(m.group(1), m.group(2), cfg, env, get)
    except (RuntimeError, OSError, ValueError, KeyError, urllib.error.URLError) as e:
        return Finding(ASK, NAME, f"`{shown}`: cannot read what is deployed ({e}). Push without the check?")
    if not deployed:
        return None
    if cfg.get("fetch", True):
        run_git(cwd, "fetch", "-q", fetch_from or "origin", timeout=30)
    problems, unknown = [], []
    for t in guarded:
        rc, local = run_git(cwd, "rev-parse", "--verify", "-q", f"{t.src}^{{commit}}")
        if rc != 0 or not local:
            unknown.append(f"cannot resolve the pushed commit {t.src!r}")
            continue
        for d in deployed:
            if run_git(cwd, "cat-file", "-e", f"{d.sha}^{{commit}}")[0] != 0:
                unknown.append(f"{d.environment} runs {d.sha[:10]}, which is not in local history after fetch")
                continue
            if run_git(cwd, "merge-base", "--is-ancestor", d.sha, local)[0] == 0:
                continue
            _, info = run_git(cwd, "log", "-1", "--format=%h %an, %ad: %s", "--date=short", d.sha)
            _, where = run_git(cwd, "branch", "-r", "--contains", d.sha, "--format=%(refname:short)")
            _, lost = run_git(cwd, "log", "--no-merges", "--format=%h %an: %s", "-20", f"{local}..{d.sha}")
            lost_lines = "\n".join(f"    {line}" for line in lost.splitlines()) or "    (merge commits only)"
            problems.append(
                f"- pushing {t.dst} ({local[:7]}) replaces {d.environment} ({d.state}, {d.release or 'no release name'}): {info}\n"
                f"  that commit is on: {', '.join(where.split()) or '(no remote branch)'}\n"
                f"  missing from your push:\n{lost_lines}")
    if problems:
        msg = ("deploy-guard: this push would deploy code without changes that are on the shared environment now.\n"
               + "\n".join(problems)
               + "\nMerge that branch into yours first (git merge <branch>). If the human confirms those changes "
                 "can go, prefix the push with GUARDRAILS_ASK=1.")
        if ask_requested(cmd):
            return Finding(ASK, NAME, msg + "\n(GUARDRAILS_ASK=1: asking the human instead of blocking)")
        return Finding(DENY, NAME, msg)
    if unknown:
        return Finding(ASK, NAME, f"`{shown}`: " + "; ".join(unknown) + ". Push without the check?")
    return None


def check(commands: list[Simple], env: dict[str, str], cfg: dict, get: HttpGet = http_get) -> list[Finding]:
    findings = []
    for cmd in commands:
        if cmd.name != "git":
            continue
        dcfg = cfg.get("deploy_guard")
        if not dcfg:
            continue
        f = check_push(cmd, dcfg, env, get)
        if f:
            findings.append(f)
    return findings
