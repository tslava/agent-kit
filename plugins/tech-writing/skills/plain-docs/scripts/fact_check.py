#!/usr/bin/env python3
"""Compare the hard facts of a source document with its rewrite. Stdlib only, Python 3.9+.

A rewrite must keep every number and every identifier of the source, and it must not
add new ones without a reason. This script finds both kinds of difference:

  MISSING  a number, code span or identifier that the source has and the rewrite lacks
  NEW      one that the rewrite has and the source lacks (a possible invention)

What counts as a hard fact:
  - the content of each code span (`fw_slot_b`),
  - each identifier outside code: a word with a digit or an underscore, or in capitals
    (Ed25519, SHA-256, ROLLED_BACK, HTTP),
  - each number (40, 3.2, 120). The unit is not compared, so "30 min" matches "30 minutes".

What it skips in both files: list numbers, heading numbers, and a number after a word
such as "step", "section", "paragraph", "page", "row" or "Q" (these point at places).

It compares tokens, not meaning. A fact can be present and still wrong: "retry 3 times"
and "wait 3 minutes" both contain 3. Read the rewrite against the source also.

Usage:
  fact_check.py SOURCE REWRITE [REWRITE ...]     (for example: the document and its glossary)
Exit code: 0 nothing missing, 1 something missing, 2 usage error.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CODE_SPAN = re.compile(r"`([^`\n]+)`")
IDENTIFIER = re.compile(r"(?<![\w-])[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)*(?![\w-])")
NUMBER = re.compile(r"(?<![\w.-])\d+(?:\.\d+)*(?![\w-]|\.\d)")
POINTER = re.compile(r"\b(?:steps?|sections?|paragraphs?|pages?|rows?|items?|lines?|tables?|figures?|rounds?|p\.|Q)\s*$", re.I)
LIST_MARK = re.compile(r"^\s*(?:#{1,6}\s+)?(?:\d+(?:\.\d+)*[.)]?\s+)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def is_identifier(word: str) -> bool:
    if re.fullmatch(r"Q\d+", word):
        return False  # the label of an open question
    if re.search(r"\d", word) or "_" in word:
        return True
    return len(word) >= 2 and word.isupper()


def facts(text: str) -> dict[tuple[str, str], tuple[int, str]]:
    """Map (kind, token) to the first line where it occurs."""
    found: dict[tuple[str, str], tuple[int, str]] = {}
    fence = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        if FENCE.match(raw):
            fence = not fence
            continue
        line = raw if fence else LIST_MARK.sub("", raw, count=1)

        def add(kind: str, token: str) -> None:
            found.setdefault((kind, token), (lineno, raw.strip()))

        for span in CODE_SPAN.findall(line):
            add("code", " ".join(span.split()))
        prose = CODE_SPAN.sub(" ", line)
        for match in IDENTIFIER.finditer(prose):
            if is_identifier(match.group(0)):
                add("name", match.group(0))
        for match in NUMBER.finditer(prose):
            if not POINTER.search(prose[:match.start()]):
                add("number", match.group(0))
    return found


def present(kind: str, token: str, text: str, own: dict[tuple[str, str], tuple[int, str]]) -> bool:
    if (kind, token) in own:
        return True
    if kind == "number":
        return bool(re.search(r"(?<![\w.-])%s(?![\w-]|\.\d)" % re.escape(token), text))
    return bool(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(token), text))


def compare(source: str, rewrite: str) -> tuple[list, list]:
    src, new = facts(source), facts(rewrite)
    missing = [(key, src[key]) for key in src if not present(key[0], key[1], rewrite, new)]
    added = [(key, new[key]) for key in new if not present(key[0], key[1], source, src)]
    return sorted(missing, key=lambda m: m[1][0]), sorted(added, key=lambda a: a[1][0])


def show(title: str, rows: list) -> None:
    print("%s (%d)" % (title, len(rows)))
    for (kind, token), (lineno, line) in rows:
        if len(line) > 80:
            at = max(0, line.find(token) - 30)
            line = ("..." if at else "") + line[at:at + 77] + "..."
        print("  line %-4d %-6s %-28s %s" % (lineno, kind, token, line))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[0] in ("-h", "--help"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    paths = [Path(a) for a in args]
    for path in paths:
        if not path.is_file():
            print("%s: no such file" % path, file=sys.stderr)
            return 2
    source = paths[0].read_text(encoding="utf-8")
    rewrite = "\n".join(p.read_text(encoding="utf-8") for p in paths[1:])
    missing, added = compare(source, rewrite)
    show("MISSING from the rewrite", missing)
    show("NEW in the rewrite: confirm that each one has a reason", added)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
