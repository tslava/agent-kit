---
name: plain-docs
description: Write, rewrite or check a technical document so that a reader can act on it after one read. For work plans and task breakdowns, specs, runbooks, procedures, READMEs and handover notes. Applies controlled plain English in the spirit of ASD-STE100 (short sentences, one name per thing, command-form steps, condition before action), builds a glossary, runs a bundled linter, then tests the text on a fresh reader agent that has no context. Use whenever the user says a document is hard to read, too dense or impossible to build from, asks to simplify it or "make this clear", wants docs for non-native English readers, wants tasks a developer can take as they are, or names STE, Simplified Technical English, plain English or controlled language. Triggers also on - упрости документ, сделай понятнее, трудно читать, перепиши простым языком, документ по которому можно нарезать задачи. NOT for marketing copy, blog posts or chat replies.
---

# Plain docs

Goal: a reader who was not in the room reads the document one time and knows what to do.

Three parts get you there. A short rule set shapes the text. A linter finds the mechanical faults. A reader test finds everything that the linter cannot see.

The rules come from ASD-STE100 Simplified Technical English, the controlled language of aircraft maintenance manuals. This skill is not an official STE tool. It does not include the STE dictionary, and no tool can certify a text as STE.

## 1. Name the reader and the job

Write one sentence before you write anything else: who reads the document, and what they do after they read it. Example: "A backend developer who is new to the project takes one work package and starts it without a call."

Read the answer from the request and the source material. If you cannot, ask the user. Every later decision depends on it: which terms need a definition, how much background to give, and which questions the reader test asks.

## 2. Write the glossary first

A long source gives one object three names, and the reader counts three objects. Fix the names before you fix the sentences.

1. Collect the name of each thing that the document talks about: components, files, roles, states, messages.
2. If the source uses two names for one thing, keep the shorter name and record the other name as banned.
3. If one name means two things, split it into two names and record the old name as banned.
4. Write the result to `GLOSSARY.md` next to the document. The format is in `references/glossary-format.md`.
5. If the document contains procedures, add a verb list. A step can then start only with a verb from the list.

If the project already contains a glossary, use it and add to it.

## 3. Write by the rules

The reasons and a before/after pair for each rule are in `references/rules.md`. Read that file before the first draft.

0. **Meaning first.** Do not drop a fact, a number, a condition or a doubt to satisfy another rule. If the short version loses precision, keep the long version.
1. **Steps are numbered and in command form.** One action per step. 20 words per sentence at most. Number only what the reader does. Describe what another actor does in a paragraph.
2. **Description uses short sentences.** 25 words per sentence at most. Six sentences per paragraph at most. The first sentence names the topic.
3. **Condition before action.** "If the read fails, stop."
4. **Simple tenses, active voice.** Name the actor: "The hub rejects the request."
5. **Use must, can and will.** State a doubt as a fact about what you know: "We did not test this on hardware."
6. **Complete grammar.** Keep the articles. Write full forms. Fewer words come from fewer thoughts, not from missing words.
7. **One name per thing.** Use the glossary name each time, in headings also.
8. **A verb names an action.** Write "Test the valve". Do not write `perform testing of the valve`.
9. **Three nouns in a row at most.** Split a longer chain with a preposition.
10. **No semicolons, no dashes, few parentheses.** Write two sentences, or name the relation: because, but, for example. A hyphen in a word or a name is correct: `pre-check`, `SHA-256`.
11. **One fact per table cell.** 25 words per cell at most. Use a list for three or more parallel items.
12. **A result is something a person can check.** "The endpoint returns 404 for an unknown ID", not "error handling works".
13. **Each fact in one place.** Do not repeat the steps in a summary table. Two copies drift apart, and the reader must compare them.

Do not change code, identifiers, commands, file paths, quoted errors or numbers. Put them in backticks. The linter counts each one as one word.

## 4. Lint

```bash
python3 <skill-dir>/scripts/plain_lint.py [--glossary GLOSSARY.md] <file-or-directory>
```

1. Fix each error.
2. Read each warning. Fix it, or leave it and record the reason in the report.
3. Run the linter again until it reports no errors.

Do not bend the meaning to silence the linter. If you mention a word and do not use it, put it in backticks. If you quote another document word for word, put the quote in a block quote. The title of a source section is a quote also. The linter does not check block quotes. For a longer quoted part, put it between `<!-- plain-lint: off -->` and `<!-- plain-lint: on -->`.

A clean lint run is not a clear document. The linter measures obedience to the rules. Only a reader can show that the text works.

## 5. Run the reader test

Follow `references/reader-test.md`. In short:

1. Write the questions that the reader from step 1 must answer, and write the correct answers, before the test.
2. Give a fresh agent the document and the questions. Give it nothing else.
3. Compare its answers with yours.
4. If an answer is wrong or missing, fix the document, not the question.
5. Use a new reader for each round. Stop after three rounds and report what stays open.

## 6. Report

Reply in the language of the user. Include:

- the reader and the job from step 1,
- the lint result: the number of errors, and each warning that you left with its reason,
- the reader test: the questions, and which answers were right, wrong or not stated in each round,
- each fact that you could not keep, and each place where the source was ambiguous,
- the number of words in the source and in the result,
- what is not clear yet.

## When you rewrite a document from another author

The source is evidence, not a draft.

- Keep each fact, number, condition and identifier.
- If the source contradicts itself or permits two readings, do not choose. Write both readings as an open question, with the place in the source.
- An open question can give a working assumption, so that the reader can continue. Mark it as an assumption. In the body text, point to the question and do not state the assumption as a fact.
- Do not fill a gap in the source with your own value. A topic name, an interval or a format that the source does not give is an open question.
- If the source says `should` and the context does not show a requirement or a guess, write an open question.
- Give each section a pointer to the source section that it comes from. A reader who doubts a statement can then find the original.
- Do not improve the design during the rewrite. Record design problems in a separate list.

Then compare the hard facts of the two texts:

```bash
python3 <skill-dir>/scripts/fact_check.py <source> <result> [GLOSSARY.md]
```

The script lists each number, code span and identifier that the source contains and the result does not. Put each one back, or record why it is gone. The script also lists each one that is new in the result. A new one is correct only if it points to a place in the document or comes from the user.

A dense source can become longer. Structure and open questions cost words. But a result that is three times as long as the source usually repeats itself: apply rule 13.

## Limits

- The linter knows English only. For another language, apply the rules that do not depend on English (length, one name per thing, condition first, lists, the glossary) and run the reader test.
- The linter matches patterns. It does not parse grammar, so it can miss a fault and it can flag a correct sentence. Warnings need your judgment.
- These rules delete persuasion. Do not use them for marketing copy or personal writing.
