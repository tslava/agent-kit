"""deploy-guard on real git repositories, with recorded Bitbucket API responses (no network).

History used by most tests:

    main:     A
    develop:  A - B            <- B is deployed on the "Dev" environment (type Staging)
    mine:     A - C            <- my branch does not contain B
    synced:   A - B - D        <- contains B
"""
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest

from guards import deploy
from guards.shell import parse

FIXTURES = Path(__file__).resolve().parent / "fixtures/bitbucket"
CFG = {"provider": "bitbucket", "branches": r"^(develop|feature/.+)$", "environment_type": "Staging",
       "token_env": "BB_TOKEN", "fetch": False}
ENV = {"BB_TOKEN": "test-token", "HOME": "/srv/agent-home"}


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "shop"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "dev@example.com")
    git(r, "config", "user.name", "Dev")
    git(r, "config", "commit.gpgsign", "false")
    shas = {}

    def commit(name):
        (r / f"{name}.txt").write_text(name)
        git(r, "add", ".")
        git(r, "commit", "-q", "-m", f"commit {name}")
        shas[name] = git(r, "rev-parse", "HEAD")

    commit("A")
    git(r, "checkout", "-q", "-b", "develop")
    commit("B")
    git(r, "checkout", "-q", "-b", "synced")
    commit("D")
    git(r, "checkout", "-q", "-b", "feature/mine", "main")
    commit("C")
    git(r, "remote", "add", "origin", "https://bitbucket.org/acme/shop.git")
    return r, shas


class FakeBitbucket:
    def __init__(self, shas, deployed="B", failed="C", older="A", error=None):
        self.calls = []
        self.values = {"DEPLOYED": shas[deployed] if deployed in shas else deployed,
                       "FAILED": shas.get(failed, failed), "OLDER": shas.get(older, older)}
        self.error = error

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        if self.error:
            raise self.error
        assert url.startswith("https://api.bitbucket.org/2.0/repositories/acme/shop/")
        if "/environments/" in url:
            return json.loads((FIXTURES / "environments.json").read_text())
        assert "22222222-2222-4222-8222-bbbbbbbbbbbb" in url, "only the Staging environment is queried"
        text = (FIXTURES / "deployments.json").read_text()
        for k, v in self.values.items():
            text = text.replace("{{%s}}" % k, v)
        return json.loads(text)


def check(cmd, repo_dir, fake, cfg=CFG, env=ENV):
    parsed = parse(cmd, cwd=str(repo_dir), env=env)
    return deploy.check(parsed.commands, dict(env), {"deploy_guard": cfg}, get=fake)


def test_push_without_the_deployed_commit_is_denied(repo):
    r, shas = repo
    found = check("git push origin feature/mine", r, FakeBitbucket(shas))
    assert [f.decision for f in found] == ["deny"]
    msg = found[0].message
    assert "Dev" in msg and "#411" in msg and "commit B" in msg


def test_push_that_contains_the_deployed_commit_passes(repo):
    r, shas = repo
    assert check("git push origin synced:feature/synced", r, FakeBitbucket(shas)) == []


def test_failed_deployment_is_skipped_for_the_last_successful_one(repo):
    r, shas = repo
    # newest deployment (failed) is C, which my branch has; the last successful one is B, which it lacks
    assert check("git push origin feature/mine", r, FakeBitbucket(shas))[0].decision == "deny"


def test_branch_outside_the_pattern_is_not_checked(repo):
    r, shas = repo
    fake = FakeBitbucket(shas)
    assert check("git push origin feature/mine:hotfix", r, fake) == []
    assert fake.calls == []


def test_push_without_refspec_uses_the_current_branch(repo):
    r, shas = repo
    found = check("git push", r, FakeBitbucket(shas))
    assert found and found[0].decision == "deny"


def test_push_without_refspec_follows_the_upstream_name(repo):
    r, shas = repo
    git(r, "checkout", "-q", "-b", "local-name", "feature/mine")
    git(r, "config", "branch.local-name.remote", "origin")
    git(r, "config", "branch.local-name.merge", "refs/heads/develop")
    git(r, "config", "push.default", "upstream")
    found = check("git push", r, FakeBitbucket(shas))
    assert found and found[0].decision == "deny" and "pushing develop" in found[0].message


def test_options_with_values_do_not_shift_the_refspec(repo):
    r, shas = repo
    found = check("git push -o ci.skip --push-option x=1 origin feature/mine", r, FakeBitbucket(shas))
    assert found and found[0].decision == "deny"


def test_head_refspec_and_git_dash_c(repo):
    r, shas = repo
    found = check(f"git -C {r} push origin HEAD", r.parent, FakeBitbucket(shas))
    assert found and found[0].decision == "deny"


def test_unresolvable_source_asks_instead_of_passing(repo):
    r, shas = repo
    found = check("git push origin no-such-branch:develop", r, FakeBitbucket(shas))
    assert [f.decision for f in found] == ["ask"]


def test_deployed_commit_missing_locally_asks(repo):
    r, shas = repo
    found = check("git push origin feature/mine", r, FakeBitbucket(shas, deployed="f" * 40))
    assert [f.decision for f in found] == ["ask"]
    assert "not in local history" in found[0].message


@pytest.mark.parametrize("error", [urllib.error.URLError("timed out"), OSError("connection reset"),
                                   urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)])
def test_api_failure_asks(repo, error):
    r, shas = repo
    found = check("git push origin feature/mine", r, FakeBitbucket(shas, error=error))
    assert [f.decision for f in found] == ["ask"]
    assert "cannot read what is deployed" in found[0].message


def test_missing_token_asks(repo):
    r, shas = repo
    found = check("git push origin feature/mine", r, FakeBitbucket(shas), env={"HOME": "/srv/agent-home"})
    assert [f.decision for f in found] == ["ask"] and "BB_TOKEN" in found[0].message


def test_push_all_asks(repo):
    r, shas = repo
    assert [f.decision for f in check("git push --all origin", r, FakeBitbucket(shas))] == ["ask"]


def test_delete_and_dry_run_are_not_checked(repo):
    r, shas = repo
    fake = FakeBitbucket(shas)
    assert check("git push origin --delete feature/old", r, fake) == []
    assert check("git push -n origin feature/mine", r, fake) == []
    assert fake.calls == []


def test_ask_prefix_turns_deny_into_question(repo):
    r, shas = repo
    found = check("GUARDRAILS_ASK=1 git push origin feature/mine", r, FakeBitbucket(shas))
    assert [f.decision for f in found] == ["ask"]


def test_non_bitbucket_remote_is_ignored(repo):
    r, shas = repo
    git(r, "remote", "set-url", "origin", "https://github.com/acme/shop.git")
    fake = FakeBitbucket(shas)
    assert check("git push origin feature/mine", r, fake) == []
    assert fake.calls == []


def test_auth_header(repo):
    r, shas = repo
    fake = FakeBitbucket(shas)
    check("git push origin synced:develop", r, fake)
    assert fake.calls[0][1]["Authorization"] == "Bearer test-token"
    fake = FakeBitbucket(shas)
    check("git push origin synced:develop", r, fake, cfg={**CFG, "user_env": "BB_USER"},
          env={**ENV, "BB_USER": "dev@example.com"})
    assert fake.calls[0][1]["Authorization"].startswith("Basic ")


def test_no_config_means_off(repo):
    r, shas = repo
    parsed = parse("git push origin feature/mine", cwd=str(r), env=ENV)
    assert deploy.check(parsed.commands, ENV, {}, get=FakeBitbucket(shas)) == []


def test_repo_option_makes_every_positional_a_refspec(repo):
    r, shas = repo
    found = check("git push --repo=origin feature/mine", r, FakeBitbucket(shas))
    assert found and found[0].decision == "deny"


class PagedBitbucket(FakeBitbucket):
    """Environments on two pages; 60 failed deployments before the successful one."""

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        if "/environments/" in url:
            if "page=2" in url:
                return json.loads((FIXTURES / "environments.json").read_text())
            return {"values": [], "next": url + "&page=2"}
        page = int(url.rsplit("page=", 1)[1]) if "&page=" in url else 1
        if page < 2:
            values = [{"state": {"name": "COMPLETED", "status": {"name": "FAILED"}},
                       "release": {"name": f"#9{i}", "commit": {"hash": self.values["FAILED"]}}} for i in range(50)]
            return {"values": values, "next": url + "&page=2"}
        values = [{"state": {"name": "COMPLETED", "status": {"name": "FAILED"}},
                   "release": {"name": "#8", "commit": {"hash": self.values["FAILED"]}}}] * 10
        values.append({"state": {"name": "COMPLETED", "status": {"name": "SUCCESSFUL"}},
                       "release": {"name": "#411", "commit": {"hash": self.values["DEPLOYED"]}}})
        return {"values": values}


def test_pagination_is_followed(repo):
    r, shas = repo
    fake = PagedBitbucket(shas)
    found = check("git push origin feature/mine", r, fake)
    assert [f.decision for f in found] == ["deny"] and "#411" in found[0].message
    assert sum("/deployments/" in u for u, _ in fake.calls) == 2


def test_too_many_pages_asks(repo, monkeypatch):
    r, shas = repo
    monkeypatch.setattr(deploy, "MAX_PAGES", 1)
    found = check("git push origin feature/mine", r, PagedBitbucket(shas))
    assert [f.decision for f in found] == ["ask"] and "more than 1 pages" in found[0].message


def test_environment_without_successful_deployments_is_not_protected(repo):
    r, shas = repo

    def get(url, headers):
        if "/environments/" in url:
            return json.loads((FIXTURES / "environments.json").read_text())
        return {"values": [{"state": {"name": "COMPLETED", "status": {"name": "FAILED"}},
                            "release": {"name": "#1", "commit": {"hash": shas["B"]}}}]}

    assert check("git push origin feature/mine", r, get) == []
