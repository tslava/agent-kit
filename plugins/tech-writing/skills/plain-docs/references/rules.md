# The rules, with reasons

Each rule has a reason and an example. If a case does not fit a rule, apply the reason.

The "before" examples are in block quotes, because the linter does not check block quotes.

## 0. Meaning first

A rewrite that loses a condition is worse than a long sentence. The limits in the other rules are tools, and rule 0 decides when a tool does not apply.

A doubt is content. Keep "not verified", "we assume" and "the source does not say". Write the doubt as a fact about what you know, not as a weak verb.

> The update might fail on older boards.

We tested the update on revision C only. We do not know the result for revisions A and B.

## 1. Steps are numbered and in command form

A reader follows a procedure with one finger on the page. One action per step lets the reader stop and continue. A numbered list tells the reader that the order is important.

- One action per step. Two actions that occur at the same time can share a step.
- 20 words per sentence at most.
- A step can contain a second sentence that gives the result or the reason.

> The slot should be erased and then the firmware image needs to be written, after which verification of the checksum is performed.

1. Erase the slot.
2. Write the firmware image.
3. Compare the checksum with the value in the notification. The values must be equal.

## 2. Description uses short sentences

A long sentence makes the reader hold the first half in memory. Most readers of technical text read in a second language, and each clause adds load.

- 25 words per sentence at most.
- Six sentences per paragraph at most.
- One topic per paragraph. The first sentence names the topic.

Count a code span, a number, a unit or a URL as one word.

## 3. Condition before action

A reader does the action when they read it. If the condition comes after the action, the reader acts first.

> Stop the job if the read fails.

If the read fails, stop the job.

## 4. Simple tenses, active voice

Passive voice hides the actor. In a system with many parts, "who does this" is the question that the reader has most frequently.

> The valve is closed after the request has been approved.

An operator approves the request. Then the node closes the valve.

Use the present, the past and the future tense. Do not use `has been` or `had done`. Do not attach an "-ing" clause to the end of a sentence after a comma. Start a new sentence.

A participle that describes a state is correct: "The valve is closed." The linter reports each such case as a warning, and you decide.

## 5. Use must, can and will

The word `should` has two readings: a requirement and a guess. A developer who reads `the service should retry` cannot tell if the retry is a requirement.

- A requirement: must.
- An ability or a permission: can.
- A future fact: will.

If `should` marks an option, delete the sentence or write the condition that decides.

## 6. Complete grammar

Telegraph style saves words and costs meaning. "Check valve open" has three readings.

Keep "the", "a" and "that". Write "do not", not the short form. To use fewer words, say fewer things: delete the introduction, the repeat and the sentence that states the obvious.

## 7. One name per thing

This rule has the largest effect. If a document says "node", "unit" and "controller", the reader looks for three objects.

- Use the glossary name each time. Do not change the word for style.
- Use the name in headings and in tables also.
- If you need a new name, add it to the glossary first.
- Write an identifier from the code in backticks. An identifier is not prose, and the linter does not check it.

## 8. A verb names an action

A noun in the place of a verb adds an empty verb and hides the action.

> Perform validation of the token and make a decision on the retry.

Validate the token. Then decide if you retry.

## 9. Three nouns in a row at most

The reader cannot tell which noun describes which.

> the node firmware download retry timeout value

the timeout of a download retry

The linter cannot find this fault. Look for it yourself.

## 10. No semicolons, no dashes, few parentheses

Each of these marks joins two thoughts and does not name the relation between them. Write two sentences. If the relation is important, name it: because, but, then, for example.

Use parentheses for a short reference only, such as a page number. A fact in parentheses looks optional, and readers skip it.

## 11. One fact per table cell

A table is for lookup. A cell that contains a paragraph cannot be scanned. If a cell needs more than 25 words, the content is not a table: write a section for each row.

Use a list for three or more parallel items. Do not use a list to break one sentence into parts.

## 12. A result is something a person can check

"Works correctly" cannot be tested. Write what a person observes when the work is complete.

> Done when: the update is robust and error handling works.

Done when: a node with a low battery rejects the update, and the status topic shows one `REJECTED_BATTERY` message.

## Notes and warnings

A note gives information. Do not put an instruction in a note, because readers skip notes.

A warning starts with the command and then gives the risk. "Do not erase the slot during a download. The node loses the new image, and the download starts again."
