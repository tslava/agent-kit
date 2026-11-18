# guardrails

One `PreToolUse` hook on the Bash tool that runs three guards before a command runs:

| Guard | Stops | Why |
|---|---|---|
| `codex-guard` | `codex exec` without a read-only sandbox, `approval_policy="never"`, Codex plugins off and stdin closed | A Codex run with approvals on rejected every shell command and then used computer-use tools to type into the user's terminals |
| `destructive-guard` | recursive `rm` outside temp dirs, `find -delete`, `find -exec rm`, `git reset --hard`, `git clean -f`, `git checkout -- <paths>`, `git restore`, `git push --force` | These lose work that git cannot give back |
| `deploy-guard` | a push that would redeploy a shared environment without the commit deployed there now | On a shared dev stand, one person's push silently removes another person's changes |

The background, and where hooks stop being enough, is in [docs/enforcement.md](../../docs/enforcement.md).

## Install

```
/plugin marketplace add tslava/agent-kit
/plugin install guardrails@agent-kit
```

Needs `python3` (3.10+) and `git` on `PATH`. No third-party packages.

## Decisions

Each guard answers one of three ways:

- **deny**: the command matches a rule and its target is known. The reason says what to do instead.
- **ask**: the guard cannot tell what the command will do (`$VAR` in a path, `eval "$X"`, `curl … | bash`, an API that did not answer). Claude Code asks the human.
- **allow**: nothing matched.

The guard never answers "allow" because it failed. If the hook itself crashes or its config is broken, it answers "ask".

### Getting past a deny

- `GUARDRAILS_ASK=1 <command>` turns that command's deny into a question to the human. The agent can type this prefix too, so it only ever leads to a prompt, never to a silent pass.
- `GUARDRAILS_OFF=codex,destructive,deploy` (or `all`) in the environment Claude Code starts with switches guards off. The agent cannot change that environment from the Bash tool.

## Config

Optional. `~/.claude/guardrails.json`, with the project's `.claude/guardrails.json` on top:

```json
{
  "destructive_guard": {"extra_safe_roots": ["build", "dist"]},
  "codex_guard": {"disable_mcp": ["my-browser-server"]},
  "deploy_guard": {
    "provider": "bitbucket",
    "branches": "^(develop|feature/.+)$",
    "environment_type": "Staging",
    "token_env": "BITBUCKET_API_TOKEN",
    "user_env": "BITBUCKET_USER"
  }
}
```

- `extra_safe_roots`: directories where recursive deletes are fine, besides the temp dirs. Relative paths are relative to the command's working directory. Only paths *inside* a root pass, not the root itself.
- `disable_mcp`: MCP servers from your own `~/.codex/config.toml` that must be off for `codex exec`. List only servers that exist: Codex refuses to start when `-c mcp_servers.<name>.enabled=false` names an unknown server.
- `deploy_guard`: off when absent. `environments: ["Dev"]` selects environments by name instead of type. `fetch: false` skips the `git fetch` before the check.

## How each guard decides

**codex-guard.** For `codex exec` and `codex exec resume`, it requires:

- `-s read-only` (for `resume`, `-c sandbox_mode="read-only"`);
- `-c approval_policy="never"`;
- `-c features.plugins=false` or `--disable plugins`;
- `-c mcp_servers.<name>.enabled=false` for each name in `disable_mcp`;
- stdin redirected or piped (`< /dev/null`).

It denies `--dangerously-bypass-approvals-and-sandbox`, `--approve-for-me`, `--full-auto` and `--yolo`. A profile (`-p`) does not count, because the hook cannot see what the profile sets. The deny reason contains the same command with the missing options added, and that command passes the guard (tested). When the input comes from a pipe, the suggestion starts with `<the same input> |`: keep your pipe in front of it.

**destructive-guard.** It reads paths after `~`, `$HOME` and `$TMPDIR` are expanded and symlinks are resolved. A recursive delete is allowed only strictly inside `/tmp`, `/private/tmp`, `/var/tmp`, the system temp dir, `$TMPDIR` or `extra_safe_roots`. Other paths are denied. Paths that depend on run-time values get "ask". `git push --force-with-lease` is allowed on purpose, `+refspec` is not.

**deploy-guard.** For each branch the push updates that matches `branches`:

1. Find the commit deployed on each watched environment: the newest deployment that is in progress or finished successfully. Failed and stopped deployments are skipped.
2. Require that commit to be an ancestor of the commit being pushed.

The pushed commit comes from the refspec. A push without a refspec uses `push.default` and the branch's upstream. If the guard cannot read the deployments (no token, API error, timeout, rate limit), it asks. It also asks when the deployed commit is missing locally after `git fetch`, or the pushed commit cannot be resolved. Only Bitbucket Cloud is supported now.

## How commands are read

`scripts/guards/shell.py` splits a command line into simple commands. It is a small reader for the forms agents use, not a shell:

- quotes, `;`, `&&`, `||`, pipes, `cd`, redirects and here-docs;
- `$(…)`, backticks and `<(…)`: their inner commands are read too, because they run;
- `sh -c`/`bash -c`, `eval`, `env -S`, `xargs`, `find -exec`;
- wrappers such as `sudo`, `timeout`, `nice`, `env` and `command`.

Text inside quotes is data. `git commit -m "rm -rf"` passes, and so does a quoted here-doc. Whatever it cannot follow gives "ask".

## Not caught

A hook sees the command string, not what the command does. These are allowed by design or because the hook cannot see them; the tests assert each one:

| Command | Why it passes |
|---|---|
| `python3 -c 'import shutil; shutil.rmtree("data")'` | Code in another language is not read |
| `node -e 'require("fs").rmSync("data", {recursive: true})'` | Same |
| `bash ./cleanup.sh` | The script file is not read |
| `make clean` | Build tools run their own commands |
| `git stash drop` | Not on the list: the stash can be recovered for a while via `git fsck` |
| `git branch -D feature` | Not on the list: the reflog keeps the commits |
| `git checkout src/app.py` | Without `--` git cannot tell a file from a branch, and neither can the guard |
| `mv data /dev/null` | Not on the list |

The same limit applies to `codex-guard`: a wrapper script that calls `codex` is not inspected. For that reason the planning plugin's `run-codex.sh` passes the controls itself. For real isolation use a boundary the agent cannot talk its way past: see [docs/enforcement.md](../../docs/enforcement.md).

## Tests

`tests/test_guardrails_*.py` and `tests/test_run_codex.py`:

- **destructive-guard and codex-guard:** tables of commands that are denied, allowed, asked about, and not caught. The not-caught rows must also be listed in this README.
- **The hook as a subprocess:** event JSON on stdin, the decision JSON on stdout, broken input and broken config.
- **deploy-guard:** real git repositories with recorded Bitbucket API responses, no network. Covers ancestry, failed deployments, `push.default=upstream`, options with values, API errors, a missing token, `--all`, deletes and dry runs.
