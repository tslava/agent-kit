# agent-kit

Plugins for AI coding agents: skills, commands, agents and hooks that come out of real
engineering work. Each plugin covers one topic. The skills are plain `SKILL.md`
files, so they work in Claude Code and in other agents that read the
[Agent Skills](https://agentskills.io) format.

## Plugins

### `python-lambda`: modernize Python services on AWS Lambda

For teams that still run Python Lambdas from 2019–2021 (Python 3.9, Pipenv, pydantic 1,
SQLAlchemy 1.3, Chalice, aws-cdk v1) and need to move them forward without breaking
production.

| Skill | What it does |
|---|---|
| [`modernize-python-lambda`](plugins/python-lambda/skills/modernize-python-lambda/SKILL.md) | The orchestrator. Python 3.14 + uv + pydantic v2 + SQLAlchemy 2.0 + aws-cdk v2 + linters + CI image, in an order where every step stays green |
| [`chalice-to-fastapi`](plugins/python-lambda/skills/chalice-to-fastapi/SKILL.md) | Chalice → FastAPI on Mangum behind the same API Gateway, with the gotchas that break real migrations |
| [`pydantic-v2-migration`](plugins/python-lambda/skills/pydantic-v2-migration/SKILL.md) | pydantic v1 → v2: what the renames miss (Optional-without-default, validator modes, stricter coercion, the new error shape) |
| [`sqlalchemy-v2-migration`](plugins/python-lambda/skills/sqlalchemy-v2-migration/SKILL.md) | SQLAlchemy 1.x → 2.x, sorted by how it fails: writes that silently stop being saved, then every loud break with its error text and fix |
| [`chalice-query-params-expand`](plugins/python-lambda/skills/chalice-query-params-expand/SKILL.md) | Fix Chalice's silent last-value-wins on repeated query params, including direct Lambda-to-Lambda invokes |
| [`dependency-cooldown`](plugins/python-lambda/skills/dependency-cooldown/SKILL.md) | Make the resolver ignore releases younger than N days (uv `exclude-newer`, Poetry `min-release-age`) |
| [`fastapi-pydantic-patterns`](plugins/python-lambda/skills/fastapi-pydantic-patterns/SKILL.md) | Conventions for FastAPI + pydantic v2 endpoints, query models, validators and response envelopes |

### Workflow plugins

The planning and review loop I use for non-trivial changes.

| Plugin | What it does |
|---|---|
| [`planning`](plugins/planning/) | `/planning:make` writes an implementation plan and gets it reviewed; `planning:exec` runs it task by task with subagents, internal review and an external code review |
| [`brainstorm`](plugins/brainstorm/) | A design dialogue before any significant change: one question at a time, approaches, design, then a plan |
| [`thinking-tools`](plugins/thinking-tools/) | `ask-codex` for a second opinion from OpenAI Codex, dialectic analysis, root-cause investigation |

## Install

In Claude Code:

```bash
/plugin marketplace add tslava/agent-kit
/plugin install python-lambda@agent-kit
/plugin install planning@agent-kit
/plugin install brainstorm@agent-kit
/plugin install thinking-tools@agent-kit
```

If another installed plugin is already called `planning`, `brainstorm` or `thinking-tools`,
uninstall it first: both would register the same skill names.

Then just describe the job, e.g. "move this Lambda to Python 3.14" or "get this API off
Chalice". The matching skill loads on its own.

## Why "just bump Python" is never one change

Python 3.14 forces the rest. pydantic 1.8 doesn't even import there. On the
[legacy example](examples/legacy-lambda/) the test suite stops at model definition time:

```
pydantic.errors.ConfigError: Validators defined with incorrect fields: positive
```

So the orchestrator plans the whole chain (uv, pydantic v2, SQLAlchemy 2.0, aws-cdk v2,
CI image) and verifies after every step.

### What a run looks like

An agent ran `modernize-python-lambda` on the legacy example from the public skill text
alone ([run log](examples/legacy-lambda/RUN-LOG.md)):

- before: 5 tests green on Python 3.9; after: the same 5 tests green on Python 3.14.6
  (pydantic 2.14, SQLAlchemy 2.1, aws-cdk-lib 2.274, uv with a 15-day cooldown);
- five traps the skill warns about fired, one after another. Optional-without-default
  turned every response into a 500, even on the 400 path. `engine.connect()` stopped
  committing, so the seed fixture silently inserted nothing, and the empty tables hid the
  `Model(**row)` error until the commit was fixed;
- the run also found 12 defects in the skill text itself (a missing Node requirement, a
  vague linter step, a CI example with no usable image, …). All of them are fixed, and the
  log lists each one.

## One gotcha, in full: the FastAPI session deadlock

After a Chalice → FastAPI port, the test suite hangs forever in fixture teardown, at
`metadata.drop_all()`.

FastAPI runs **sync** handlers in a worker thread. The thread-local `scoped_session`
opens its transaction in *that* thread. Cleanup in an async middleware runs in the
event-loop thread and removes the wrong thread's session. The transaction stays open
holding a lock, and `DROP TABLE` waits forever.

The fix is to clean up in the handler's own thread, without hiding its signature from
FastAPI's dependency injection:

```python
def close_session(session):
    def decorator(fn):
        @functools.wraps(fn)           # FastAPI still sees fn's real parameters
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            finally:
                session.remove()       # same worker thread as fn
        return wrapper
    return decorator
```

The skill carries a dozen more like this: the 20 KB Lambda resource-policy limit,
which makes enumerated API Gateway routes fail to deploy; cold-start timeouts at 128 MB;
a Lambda outside the VPC that serves `/docs` but returns 502 on every DB route.

## How the python-lambda skills are written

- **Orchestrator + focused skills.** One skill owns the order of operations and links to
  narrow skills for each domain, so each stays short enough to follow.
- **Every gotcha carries its cause.** "Use `engine.begin()`" is a rule. "`engine.connect()`
  stopped autocommitting, so your seed fixture silently inserts nothing" is a rule you can
  apply to a case the skill never saw.
- **Verify after each step.** A green step is the base for the next one.
- **Tested on a fixture.** The legacy example is run through the skills, and the run log
  records the defects found in the skill text itself.

More in [docs/how-these-are-written.md](docs/how-these-are-written.md).

## Other tools I use

Not in this repo, but part of the same workflow:

- [Plannotator](https://github.com/backnotprop/plannotator): review and annotate plans and
  diffs in the browser, and send the annotations back to the agent.
- From Anthropic's [official plugins](https://github.com/anthropics/claude-plugins-official):
  `skill-creator` (writing skills and their evals, the format the evals here follow),
  `frontend-design` and `playground`.

## Repository layout

```
.claude-plugin/marketplace.json   # the marketplace
plugins/<plugin>/                 # one plugin per topic
  .claude-plugin/plugin.json
  skills/<skill>/SKILL.md (+ references/, scripts/)
  commands/, agents/, hooks/        # where a plugin has them
  LICENSE                           # where a plugin has its own license
examples/                         # synthetic fixtures and run logs
scripts/lint_skills.py            # frontmatter, links, hygiene checks
tests/                            # tests for bundled scripts
```

CI runs the linter, the script tests and a secret scan on pushes to `main` and on pull requests.

## License

[MIT](LICENSE). A plugin folder with its own `LICENSE` file is covered by that file.

---

Built by Wiaczeslaw Cyunczyk · [tslava.github.io](https://tslava.github.io/)
