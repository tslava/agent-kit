# plain-docs

A skill for AI coding agents. It writes or rewrites a technical document so that a reader can act on it after one read.

Use it for the document that is complete and still impossible to build from. One component has three names. A table cell holds a paragraph. The text gives two values for one timeout, and nobody sees it.

## When to use it

- An LLM wrote the document: it is long, and it states guesses as facts.
- A consultant sent a document, and you cannot judge the work.
- You must split a spec into tasks for several developers.
- An agent will read the document: a prompt, a brief, an `AGENTS.md` file.
- A mistake in the procedure is expensive: a runbook, a migration.

## What it costs and what it saves

The writer pays one time: 1.6 times the tokens in the test below. Each reader saves after that, because nobody stops at an unclear name or builds from a value that the author never gave. We measured the cause, not the saving: 7 invented values without the skill, none with it.

## What it does

The skill has four parts.

| Part | What it gives you |
|---|---|
| Rules | 14 short rules in the spirit of ASD-STE100 Simplified Technical English: steps of 20 words, one name for each thing, the condition before the action. |
| Glossary | One file with the names and their banned synonyms. The reader learns the names from it, and the linter enforces it. |
| Two scripts | `plain_lint.py` finds the mechanical faults. `fact_check.py` finds each number and identifier that a rewrite lost or invented. |
| Reader test | A fresh agent gets only the document and a list of questions. A wrong answer shows where the text fails. |

## Before and after

> The slot should be erased and then the firmware image needs to be written, after which verification of the checksum is performed.

1. Erase the slot.
2. Write the firmware image.
3. Compare the checksum with the value in the notification. The values must be equal.

## What the linter says

A glossary with two names and six verbs:

```markdown
## Names

| Use | Not | Meaning |
|---|---|---|
| node | unit, controller, device | The box in the field that opens and closes one valve. |
| hub | gateway | The box at the site that relays messages to the nodes. |

## Verbs

check, erase, read, report, send, write
```

A text that ignores it:

```markdown
The unit should only begin the procedure when it's safe; the gateway pre-validates the image.

1. Download the image if the battery is not below 40 %.
```

A part of the output:

```text
update.md:3: error [contraction] write the full form: "it's"
update.md:3: error [semicolon] write two sentences: ";"
update.md:3: error [term] use "node": "unit"
update.md:3: error [term] use "hub": "gateway"
update.md:5: warning [trailing-condition] put the condition first: "If X, do Y.": "Download the image if the battery is not below 40 %."
```

The scripts need Python 3.9 or later and nothing else. You can run them without an agent:

```bash
python3 scripts/plain_lint.py --glossary GLOSSARY.md docs/
python3 scripts/fact_check.py source.md rewrite.md GLOSSARY.md
```

## What a test run showed

Two agents rewrote one dense spec section of 430 words. One used the skill. Then a fresh reader answered the same 10 questions on each result.

| | With the skill | Without the skill |
|---|---|---|
| Reader answers that agree with the key | 10 of 10 | 10 of 10 |
| Facts in the body that the source does not give | 0 | 7 |
| Open questions for the author | 12 | 7, each with a chosen answer |
| Linter errors | 0 | 7 |
| Time | about 11 minutes | 32 seconds |

The skill did not make the text easier to understand. A current model writes clear prose without help.

The skill changed what the text states as fact. Without it, the agent filled each gap of the source with a value of its own. With it, each gap became a question for the author. That is the important difference for a document that a team builds from.

The full log, with both results and the 14 defects that the run found in the skill, is in [examples/dense-spec](../../../../examples/dense-spec/RUN-LOG.md).

## Install

In Claude Code:

```bash
/plugin marketplace add tslava/agent-kit
/plugin install tech-writing@agent-kit
```

For another agent that reads the Agent Skills format, copy this folder into its skills folder.

Then describe the job. Examples: "this spec is impossible to build from, rewrite it for a new developer", "make this runbook clear", "check this document against the rules".

## Files

| File | Content |
|---|---|
| [SKILL.md](SKILL.md) | The workflow: reader, glossary, rules, lint, reader test, report. |
| [references/rules.md](references/rules.md) | Each rule with its reason and an example. |
| [references/glossary-format.md](references/glossary-format.md) | The format of the glossary file, and how the linter matches names. |
| [references/reader-test.md](references/reader-test.md) | The reader test: questions, the prompt for the reader, how to compare. |
| [scripts/plain_lint.py](scripts/plain_lint.py) | The linter. |
| [scripts/fact_check.py](scripts/fact_check.py) | The fact check between a source and its rewrite. |

## Limits

- The linter knows English only. It matches patterns and does not parse grammar.
- A clean lint run shows that the text obeys the rules. Only the reader test shows that the text works.
- The run above is one example and one run. It is not a benchmark.
- The rules delete persuasion. Do not use them for marketing copy.

## Credits

This is not an official tool for [ASD-STE100](https://www.asd-ste100.org/), and it does not include the dictionary of the standard. No tool can certify a text as STE.

Two ideas come from other projects. The linter checks follow [SimpleEnglish](https://github.com/AminBlg/SimpleEnglish). The reader test follows the reader testing stage of the `doc-coauthoring` skill in [anthropics/skills](https://github.com/anthropics/skills).
