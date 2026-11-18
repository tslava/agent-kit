# Keeping AI coding agents inside the lines

A rule for an AI agent can live in three places. Each one gives a different guarantee. Teams adopting agents often treat the first as if it were the third.

## Three levels

| Level | What it does | What it guarantees | Examples in this repo |
|---|---|---|---|
| **Instructions** | `CLAUDE.md`, `AGENTS.md`, skills. They steer the model. | Nothing. They usually work, but the model can skip or forget one, or decide it does not apply. | Codex launch rules in the [`ask-codex`](../plugins/thinking-tools/skills/ask-codex/SKILL.md) skill |
| **Interception** | Hooks and `permissions.deny` check each tool call before it runs. | The decision holds for every call the hook actually sees. Coverage depends on the matcher and on how the action is reached: a wrapper script, an interpreter or a variable can carry the same action past a check that reads command text. | [`guardrails`](../plugins/guardrails/) (`codex-guard`, `destructive-guard`, `deploy-guard`); the plan-review hook in [`planning`](../plugins/planning/) |
| **Boundary** | The OS or a service enforces it: sandbox, credential scope, repository permissions, branch protection, required CI checks. | It holds whatever the model does, but only for the resources and actions it covers. Check that scope separately. | Read-only cloud credentials for the agent; `codex exec -s read-only` (an OS sandbox for Codex); protected branches with required checks |

In short: instructions shape behaviour, hooks catch the usual mistakes, and permissions and environment provide the security.

Two things are easy to put on the wrong level:

- **A flag that the agent passes itself is not a boundary for that agent.** `codex exec -s read-only` is a real OS sandbox for Codex: Codex cannot widen it from inside. Whether the flag is passed at all, though, is the calling agent's choice. A hook (`codex-guard`) makes that choice mandatory for the calls it can see.
- **Config hygiene is not a permission.** A `noreply` commit address in a per-directory `includeIf` keeps a work email out of public history. It stops nothing. A git worktree keeps edits away from your checkout, but on its own it does not stop the agent from reading or writing other files.

## Case 1: Codex in exec mode

I use OpenAI Codex as a second reviewer: Claude Code starts `codex exec` with a prompt and reads its answer.

**What happened (2026-11-02).** Codex was started without an explicit approval policy. A directory entry with `trust_level = "untrusted"` in `~/.codex/config.toml` turned approvals on. In exec mode there is nobody to approve, so every shell command was rejected ("approval is not supported in exec mode"). The model did not stop. It switched to the computer-use tools of the Codex desktop integration, clicked through terminal sessions and typed commands into my other terminals.

**First fix: an instruction.** A rule in my `CLAUDE.md`: always pass `-s read-only -c approval_policy="never"`, switch off the GUI MCP servers by name, close stdin, and after the run grep the log for the computer-use tool name.

**Second fix: interception.** The rule was easy to forget. A wrapper script in this repo called Codex with `--sandbox read-only` only. `codex-guard` now denies any direct `codex exec` that lacks the controls. The deny reason includes the same command with the missing options added. The wrapper got the same controls, because a hook that reads command text cannot see inside a script.

**What building the hook found.** To test the guard I listed which MCP servers Codex actually loads with the instruction's flags (`codex mcp list --json`, codex-cli 0.169.0). The tool that typed into the terminals, `cua_repl`, was still enabled. It comes from a bundled Codex plugin, not from `config.toml`, so switching servers off by name does not reach it. Trying to switch it off by name stops Codex from starting at all ("invalid transport"), as it does for any server name Codex does not know. `-c features.plugins=false` removes it. The instruction had a hole that nobody noticed until a test checked the result instead of the flags.

Lesson for teams: test the effect of a control (which tools the process really has), not only that the control is present (which flags were passed).

## Case 2: one shared dev environment

Several developers push feature branches, and every push to those branches redeploys the same dev stand. If my branch does not contain the commit that is deployed now, my push replaces the stand and silently removes a colleague's change. An agent that pushes after finishing a task does this without a second thought.

`deploy-guard` asks the CI provider what is deployed on each watched environment. It denies the push when that commit is not an ancestor of the commit being pushed. The deny reason names the environment, the release, the commit, the branches that contain it, and the commits that would disappear.

If the guard cannot check (no token, API down, rate limit, a commit it cannot resolve), it asks the human. It never treats "could not check" as "safe".

This is interception, not a boundary. The real boundary is deployment protection in CI, for example a rule that a deploy to a shared environment must contain the currently deployed commit. The hook gives the agent the answer early, inside its own session, where it can still merge and retry.

## Case 3: destructive commands

`destructive-guard` denies recursive deletes outside temp dirs, `git reset --hard`, `git clean -f`, discarding checkouts and force pushes. It allows `--force-with-lease`.

A command string is a weak signal. `python3 -c 'shutil.rmtree(...)'`, a cleanup script or `make clean` delete just as well, and the guard does not read them. The plugin README lists each known gap, and a test keeps that list in sync with the code. For destructive actions the boundary is what protects you:

- run the agent in a sandbox or container that only mounts the project;
- commit or stash before an agent session;
- protect shared branches on the server, so a force push is rejected there whatever the client does.

## Design rules for interception hooks

These come from writing and testing the three guards:

1. **Three answers, not two.** Deny what you are sure about and say what to do instead. Ask when the command depends on a run-time value (`$DIR`, `eval "$X"`, `curl … | bash`). Allow the rest.
2. **Fail towards the human.** In Claude Code a crashing hook does not block the call. Catch everything and answer "ask".
3. **Read structure, not substrings.** `git commit -m "remove rm -rf"` is not a delete. Read quotes, command separators, `$(…)`, `sh -c`, `xargs` and `find -exec`. Treat what you cannot read as unknown, not as safe.
4. **Bypasses must be visible.** An inline prefix the agent can type (`GUARDRAILS_ASK=1`) should only turn a deny into a question. A real off switch belongs in the environment the human starts the agent with.
5. **Publish the gaps.** A table of what the hook does not catch, enforced by tests, is worth more than a claim that it "blocks dangerous commands".
6. **Test the contract the runner uses.** Run the hook as a subprocess with the event JSON on stdin and check the JSON it prints. Use recorded API responses, not the network.

## For a team adopting agents

- Write the rules down (instructions), then move the ones that hurt when skipped into hooks, then ask which of them need a boundary.
- Give agents credentials scoped to what the task needs. Read-only by default.
- Keep protected branches and required checks on the server. They are the boundary for everything a local hook misses.
- When something goes wrong, keep the incident note and the fix together. The note explains the rule better than any comment.
