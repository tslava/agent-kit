# The reader test

You wrote the document, so you cannot read it as a new reader does. You know what each sentence is supposed to say. A fresh agent knows only what the text says.

The test gives the document to a reader with no context and asks the questions that the real reader must answer. A wrong answer shows a place where the text fails.

## 1. Write the questions and the answer key first

Write 5 to 8 questions for the reader from step 1 of the skill. Write the correct answer to each question. Save both in a scratch file outside the folder of the document, so that the reader cannot find the key.

Write the key before the test. If you read the answers of the reader first, each plausible answer looks correct.

Ask about what the reader must do, not about what the text says. Use these types:

| Type | Example |
|---|---|
| First action | What do you do first, and in which repository? |
| Boundary | What is not part of this work package? |
| Done | How do you know that the work is complete? |
| Dependency | What must exist before you start? |
| Name | What is the difference between a slot and a firmware image? |
| Open point | What is not decided yet, and who decides? |
| Number | What is the time limit of the download, and where does the value come from? |

For a long document, test each unit separately: one work package, one procedure, one section. A reader who gets 40 pages answers from the summary.

## 2. Start a fresh reader

Start a new subagent for each unit. Give it only this prompt, the file and the questions. Do not give it the answer key, the conversation or the source material.

```text
You are <the reader from step 1, for example: a backend developer who is new to this project>.

Read this file and nothing else: <path>
(If the document has a glossary file, read it also: <path>)
Use tools only to read these files.

Answer each question below from the text only.
- Quote the sentence that gives the answer.
- If the text does not give the answer, write NOT STATED. Do not guess.
- If the text permits two answers, write AMBIGUOUS and give the two answers.
- Say if the text gives the answer as a fact or as an assumption of the writer.

Then list:
- each term that the text uses and does not define,
- each sentence that you read two times to understand.

Questions:
1. ...
```

A reader that can search the repository answers from the code, and the test then measures the code. The sentence about tools in the prompt prevents that. If your agent runner can limit the tools of a subagent, limit them also.

## 3. Compare

Put each answer in one of four groups:

- **Right**: the answer agrees with the key.
- **Wrong**: the reader understood something that you did not mean.
- **Not stated**: the document does not contain the answer.
- **Ambiguous**: the text permits two readings.

A wrong answer is the most important result. The reader was sure, and a real reader builds the wrong thing.

Read the two lists also. An undefined term goes into the glossary. A sentence that the reader read two times gets a rewrite.

## 4. Fix the document, then test with a new reader

Fix the text, not the question. Do not add the answer in the words of the question, because the next reader then finds it by its words.

Sometimes the document does not contain the answer because nobody knows it. Then write an open point: the question, who can answer it, and what the reader assumes until then.

Start a new reader for the next round. A reader that saw the old text remembers it.

Stop when each answer in a round is right and no undefined term blocks an answer. The reader always lists some terms and some sentences. Fix the ones that the reader of step 1 needs for the job, and report the others. Stop after three rounds in each case, and report what stays open.

## 5. If you cannot start a subagent

Ask the user to open a new conversation, paste the document and the prompt from step 2, and give you the answers. Then continue from step 3.

## What the test does not show

- It does not show that the document is correct. A reader can understand a wrong statement perfectly. Check the facts against the source separately.
- One reader is one sample. A second reader with another role can find other faults.
