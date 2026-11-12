# AI coding-agent configuration checklist

A repository that configures a coding agent ships code that runs on every developer's machine
that opens it with the agent, often with that developer's credentials. Review it like CI
config.

## Files to read

`.claude/settings.json`, `.claude/settings.local.json` (should not be committed),
`.claude/hooks/`, `.claude/commands/`, `.claude/agents/`, `.claude/skills/`, `.mcp.json`,
`CLAUDE.md`, `AGENTS.md`, `.cursor/`, and any script or CI workflow that runs an agent CLI.

## Permissions

- Allow rules broad enough to run anything: `Bash(*)`, `Bash(curl:*)`, `Bash(python:*)`,
  write access outside the project directory.
- A committed default permission mode that skips approval (`bypassPermissions` in Claude Code
  settings), or scripts that start an agent with approval and sandbox turned off: Claude Code's
  `--dangerously-skip-permissions`, Codex CLI's `--dangerously-bypass-approvals-and-sandbox`.
- Agents started non-interactively without an explicit sandbox and approval policy. When the
  shell is unavailable or every command is rejected, an agent may fall back to whatever other
  tools it has, including GUI or browser automation. Pin a read-only sandbox for review jobs and
  disable tools the job doesn't need.

## Hooks and commands

- Hooks run shell commands automatically on agent events. Anyone who can change a hook in the
  repository changes what runs on the developer's machine. Hooks should call scripts that are
  in the repository and reviewed, not download and run code.
- Hooks or commands that read secret files, send data to external URLs, or modify files
  outside the project.

## MCP servers

- Project MCP servers launched by an unpinned package (`npx -y some-server`, `uvx some-server`
  without a version) pull whatever was published last.
- Tokens written into `.mcp.json` or into the server's command line instead of being read
  from the environment.
- Servers that give the agent write access to production systems (databases, cloud accounts,
  ticketing, messaging) where read-only would do.

## Prompt injection paths

- Agents that read untrusted text (issue bodies, PR descriptions, web pages, emails, user
  uploads) while they also hold write tools or secrets. Treat that text as an attacker's input:
  a workflow that runs an agent on `issue_comment` or `pull_request_target` with repository
  secrets is a script-injection bug with extra steps.
- Instructions in `CLAUDE.md` or `AGENTS.md` that tell the agent to read credential files or
  to paste secrets into commands.

## Secrets

- Credentials, internal hostnames or account ids in agent instructions, committed transcripts,
  memory files or plan documents. These files are easy to forget when open-sourcing a repo.
