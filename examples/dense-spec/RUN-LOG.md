# Run log: `plain-docs` on a dense spec section

The fixture is [spec.md](spec.md): one invented section of a firmware spec, 430 words. It has the faults that the skill is for. One component has five names. A table cell holds a paragraph. The text gives two values for one time limit. The word `should` hides which statements are requirements.

Task for both agents:

> This section of our spec is impossible to build from. Rewrite it so that a firmware developer who is new to the project can implement the update client on the node without a call with the author.

One agent used the skill from its public text alone. One agent had no skill. Then a fresh reader agent (a smaller model) answered the same 10 questions on each result. The questions and the answer key existed before the two runs ended.

## Result

| | With the skill | Without the skill |
|---|---|---|
| Result | [update.md](with-skill/update.md) and [GLOSSARY.md](with-skill/GLOSSARY.md) | [update.md](without-skill/update.md) |
| Words | 1414 and 359 | 1317 |
| Time | 10 min 47 s | 32 s |
| `plain_lint.py` errors | 0 | 7 |
| `plain_lint.py` warnings | 0 | 15 |
| Source facts that `fact_check.py` reports as missing | 0 | 1 |
| Facts in the body that the source does not give | 0 | 7 |
| Open questions for the author | 12 | 7, each with a chosen answer |
| Reader answers that agree with the key | 10 of 10 | 10 of 10 |

## What the numbers show

**The reader understood both results.** A current model writes clear prose with no skill. The skill did not improve the answers of the reader on this fixture.

**The difference is in what each result states as fact.** The source does not name the status topic, the wait between checks, or the rule to compare versions. It gives two download limits. The agent without the skill filled each gap in the body text: a topic name, a 5 minute interval, semantic versions, 30 minutes. It also added an erase before the download, a rule to keep the notification and check again, and a "cloud gateway" as a second component.

It listed most of the choices at the end. The reader had to follow a pointer to learn that a table row was a guess. The agent with the skill wrote each gap as a question and kept the body to what the source says.

For a document that a team builds from, this is the important difference. A developer implements the topic name that the table shows.

**The cost is real.** The run with the skill took 20 times longer. The glossary, two lint cycles and two reader rounds account for the time.

**Both results are three times as long as the source.** The source was dense, and the open questions take words. The result with the skill also repeats facts in two summary tables.

## Defects that the run found in the skill

The agent listed 14. These changed the skill:

1. The skill said "do not choose" for a contradiction, and the reader test said to write what the reader assumes. The rule now permits a marked working assumption in the open question and keeps it out of the body.
2. Nothing stopped the agent from a value of its own in a gap. The rewrite section now says that a gap is an open question.
3. The agent said that it kept each fact, and nothing verified the claim. One identifier was only in the glossary. `fact_check.py` now compares numbers, code spans and identifiers of the two texts. On the result without the skill, it finds the invented topic, the invented interval and the lost section reference.
4. The verb check ran on numbered items that described another actor. Rule 1 now says to number only what the reader does, and the linter message says the same.
5. Six of seven passive voice warnings were states such as "the valve is closed". The linter now skips common state words.
6. A banned word in the glossary rejected a correct use in another sense. The glossary reference now warns about it.
7. The reader prompt did not limit the reader to the document, and the answer key was in the same folder. The reference now covers both.
8. Both results repeated facts in summary tables. Rule 13 is new: each fact in one place.
9. The stop rule of the reader test covered answers only. It now covers the terms that block an answer.

The results in this folder come from the skill text before these fixes. The lint numbers in the table come from the linter after them.
