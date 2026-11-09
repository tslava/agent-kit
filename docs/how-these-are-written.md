# How these skills are written

A skill is a prompt that runs without you watching. These are the rules the skills in
this repo follow, and the reasons behind them.

## 1. Write down what broke, not what the docs say

The SQLAlchemy migration guide already explains `select()`. A skill earns its place with
what the guide doesn't say: what failed in a real codebase, how the failure looked, and
why it happened. For example:

> `engine.connect()` stopped autocommitting. A test fixture that seeds data inside
> `with engine.connect()` now inserts nothing: the transaction is rolled back on close.
> The failure shows up later as an empty result, not as an error.

An agent that knows the *cause* can recognize the same failure in a shape the skill never
mentions.

## 2. One orchestrator, several narrow skills

`modernize-python-lambda` owns the order of operations and the verification between steps.
pydantic, SQLAlchemy, the dependency cooldown and the framework swap each live in their own
skill. The narrow skills stay usable on their own ("just migrate pydantic"), and the
orchestrator stays short enough that the agent actually follows it.

## 3. Order so that every step is green

"Remove Chalice before bumping Python" is not style. Chalice doesn't import on the new
Python, so the other order leaves you with a broken tree and no bisectable history. Every
step ends with a check (`uv run pytest`, an import, a synth), and the next step starts only
from green.

## 4. Ask about the forks, infer the rest

Each skill lists the few decisions it cannot infer from the code (deployment shape, cutover
strategy, whether pushing deploys) and asks about them up front. Everything else it reads
from the repository instead of asking.

## 5. Descriptions are for triggering

The `description` field decides whether the agent loads the skill at all. It names the
user's likely words ("get off Chalice", "just move this lambda to 3.14"), the symptoms
("only returns the last id"), and the cases where the skill should load even though the
user named only one part of the job.

## 6. Test the skill, not only the code it produces

A skill can produce passing code and still contain wrong instructions. Each plugin gets a
synthetic fixture (`examples/`). An agent runs the skill on it from the public text alone,
and the run log records where the instructions were wrong, vague or out of date. Those
defects are fixed in the skill.

## 7. Bundle scripts for the deterministic parts

When a step has one correct result (editing `poetry.toml` idempotently, for example), the
skill ships a script with tests instead of prose. The agent spends its judgment where
judgment is needed.
