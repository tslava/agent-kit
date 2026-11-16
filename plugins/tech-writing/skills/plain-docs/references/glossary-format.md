# The glossary file

The glossary has two jobs. The reader learns the names from it. The linter reads the same file and enforces it, so the two cannot drift apart.

## Format

Save the file as `GLOSSARY.md` next to the document. The linter finds it there. For another place, pass `--glossary <file>`. If no glossary file exists, the linter looks for the two sections in the document itself.

```markdown
# Glossary

## Names

| Use | Not | Meaning |
|---|---|---|
| node | unit, controller, device | The box in the field that opens and closes one valve. |
| hub | gateway, base station | The box at the site that relays messages to the nodes. |
| firmware image | image, bundle | The file that the hub sends to a node for an update. |
| `node_id` | | The integer key of a node in the site database. |

## Verbs

add, remove, read, write, send, receive, erase, test, measure
```

## The Names table

- **Use**: the one name for the thing. Choose the shorter of two names.
- **Not**: the banned names, with commas between them. The linter reports each one as an error and gives the correct name. Leave the cell empty if no banned name exists.
- **Meaning**: one sentence that a new reader understands.

The section heading must contain the word "Names" or "Terms". The second column must have the heading "Not", "Avoid" or "Do not use".

How the linter matches:

- It ignores case, and it accepts a plural "s" or "es".
- It does not look in code spans. `unit_id` in backticks is not a use of the banned word "unit".
- A longer name in the Use column protects the words in it. If "firmware image" is a name and "image" is banned, "firmware image" passes and "image" alone fails.

## The Verbs list

The list is optional. If it exists, each numbered step must start with one of its verbs. A step can start with a condition ("If the read fails, erase ..."), with "Then", or with "Do not".

A short list forces one verb per action. If the list contains "erase", the writer cannot switch between "erase", "wipe" and "clear". Use 15 to 25 verbs for a work plan.

Add a verb when you need one. Do not write a step around a missing verb.

## What to put in the glossary

- Each component, service, file, role, state and message that the document names.
- Each word that the source uses with two meanings. Give each meaning its own name.
- Each name that is different in the code and in the document. Decide which one the document uses.

Do not add common words. A glossary of 30 to 50 names is typical for a system document.

Ban a name only if it always means the same thing as the name in the Use column. If a word is correct in another sense, do not ban the word alone. Example: with "firmware image" as the name, a ban on "firmware" also rejects "hub firmware 3.2". Ban the full phrase that you want to remove.
