#!/usr/bin/env python3
"""Lint Markdown against the plain-docs writing rules. Stdlib only, Python 3.9+.

What it checks (see ../references/rules.md for the reasons):
  errors    step-length, sentence-length, paragraph-length, cell-length,
            semicolon, dash, contraction, perfect-tense, modal, latin,
            term (a banned synonym from the glossary), step-verb
  warnings  passive, ing-clause, filler, nominalization, parenthesis,
            trailing-condition, perfect-tense (without "been")

What it reads:
  - a numbered list item is a step: 20 words per sentence, command form;
  - paragraphs, bullets and table cells are description: 25 words per sentence;
  - a paragraph holds 6 sentences at most, a table cell 25 words at most;
  - code blocks, inline code, URLs, block quotes, front matter and text between
    `<!-- plain-lint: off -->` and `<!-- plain-lint: on -->` are not checked.

The glossary is a Markdown file with a "Names" table (columns: Use | Not | Meaning)
and an optional "Verbs" list. See ../references/glossary-format.md.

This is a pattern matcher, not a parser of English. It finds the mechanical faults.
It cannot tell you that a reader understands the text: run the reader test for that.

Usage:
  plain_lint.py [--glossary FILE] [--strict] [--json] PATH [PATH ...]
Exit code: 0 clean, 1 findings (errors, or warnings with --strict), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STEP_LIMIT = 20
SENTENCE_LIMIT = 25
PARAGRAPH_LIMIT = 6
CELL_LIMIT = 25
PAREN_LIMIT = 8

IRREGULAR = (
    "given|taken|made|done|found|seen|known|shown|written|built|sent|set|run|read|kept|held|"
    "left|put|cut|lost|chosen|drawn|driven|thrown|broken|hidden|bound|begun|paid|sold|told|"
    "brought|bought|caught|taught|thought|meant|fed|led|met|won|worn|torn|stolen|spoken|"
    "frozen|forgotten|gotten"
)
# Participles that usually describe a state, not an action. "The valve is closed" is not passive voice.
STATES = (
    "un\\w+ed|closed|opened|locked|enabled|disabled|connected|disconnected|required|needed|allowed|"
    "permitted|supposed|scheduled|exhausted|finished|completed|related|based|located|installed|"
    "supported|limited|interested|done|set|known|left|lost|broken|hidden|bound"
)
RULES = [
    # (rule, level, pattern, message)
    ("semicolon", "error", re.compile(r";"), "write two sentences"),
    ("dash", "error", re.compile(r"—|\s–\s|\s--\s"), "write two sentences, or name the relation"),
    ("contraction", "error",
     re.compile(r"\b\w+n['’]t\b|\b\w+['’](?:ll|re|ve|d|m)\b|\b(?:it|that|there|here|what|who|let)['’]s\b", re.I),
     "write the full form"),
    ("perfect-tense", "error", re.compile(r"\b(?:has|have|had)\s+(?:not\s+|never\s+|already\s+)?been\b", re.I),
     "use a simple tense"),
    ("perfect-tense", "warning",
     re.compile(r"\b(?:has|have|had)\s+(?:not\s+|never\s+|already\s+)?(?:\w{3,}ed|%s)\b" % IRREGULAR, re.I),
     "if this is a perfect tense, use a simple tense"),
    ("modal", "error", re.compile(r"\b(?:[Ss]hould|[Ww]ould|[Mm]ight|[Cc]ould|may)\b"),
     "use must, can or will. State a doubt as a fact: \"We did not test X.\" To mention the word, put it in backticks"),
    ("latin", "error", re.compile(r"\b(?:e\.g\.|i\.e\.|etc\b\.?)", re.I), "write \"for example\", \"that is\", or name the items"),
    ("passive", "warning",
     re.compile(r"\b(?:is|are|was|were|be|being)\s+(?:not\s+|then\s+|\w+ly\s+)?(?!(?:%s)\b)(?:\w{3,}ed|%s)\b"
                % (STATES, IRREGULAR), re.I),
     "if this is an action, name the actor"),
    ("ing-clause", "warning",
     re.compile(r",\s+(?!(?:including|excluding|during|according|regarding|depending)\b)\w{3,}ing\b", re.I),
     "start a new sentence"),
    ("filler", "warning",
     re.compile(r"\b(?:simply|just|basically|essentially|in order to|it is worth noting|please note|note that|"
                r"leverag\w+|utiliz\w+|robust|seamless(?:ly)?|comprehensive|crucial|straightforward)\b", re.I),
     "delete it, or state the fact"),
    ("nominalization", "warning",
     re.compile(r"\b(?:perform|performs|conduct|conducts|carry out|carries out)\s+(?:an?\s+|the\s+)?"
                r"\w+(?:ing|tion|sion|ment|ance|ence)\b|\bmakes?\s+(?:a\s+decision|use\s+of)\b", re.I),
     "use the verb: \"test the valve\", not \"perform testing of the valve\""),
]
PAREN = re.compile(r"\(([^()]*)\)")
TRAILING_COND = re.compile(r"\s(?:if|when|unless)\s", re.I)
LEAD_IN = {"if", "when", "before", "after", "until", "while", "unless", "once", "for", "in", "on", "at", "with"}
NOT_HEADER = re.compile(r"^(?:not|do not use|avoid|banned)$", re.I)
ABBREVIATION = re.compile(r"(?:\be\.g\.|\bi\.e\.|\bvs\.|\bcf\.|\bapprox\.|\bNo\.|\bFig\.)$", re.I)
BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])|\n")

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
BULLET = re.compile(r"^\s*[-*+]\s+(?:\[[ xX]\]\s+)?(.*)$")
TABLE_ROW = re.compile(r"^\s*\|(.*)\|\s*$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
RULE_LINE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
VERB_LINE = re.compile(r"^\s*(?:[-*+]\s+)?`?[a-z]+`?(?:\s*,\s*`?[a-z]+`?)*\s*,?\s*$")
SWITCH = re.compile(r"<!--\s*plain-lint:\s*(on|off)\s*-->", re.I)


def clean(text: str) -> str:
    """Reduce one source line to its prose. Code and URLs become one word each."""
    text = re.sub(r"`[^`]*`", "CODE", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<https?://[^>]*>|https?://\S+", "URL", text)
    text = re.sub(r"<!--.*?-->", " ", text)
    text = re.sub(r"</?[A-Za-z][^>]*>", " ", text)
    text = re.sub(r"&#?\w+;", " ", text)
    text = re.sub(r"\*+|~~|(?<!\w)_+|_+(?!\w)", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def count_words(text: str) -> int:
    return sum(1 for token in text.split() if re.search(r"\w", token))


class Unit:
    """One block of prose: a step, a bullet, a paragraph, a table cell or a heading."""

    def __init__(self, kind: str, header: str = "") -> None:
        self.kind = kind
        self.header = header
        self.parts: list[tuple[int, str, bool]] = []

    def add(self, lineno: int, raw: str) -> None:
        hard_break = raw.endswith("  ") or raw.endswith("\\")
        text = clean(raw.rstrip("\\"))
        if text:
            self.parts.append((lineno, text, hard_break))

    def joined(self) -> tuple[str, list[tuple[int, int]]]:
        out, starts, pos = [], [], 0
        for lineno, text, hard_break in self.parts:
            starts.append((pos, lineno))
            out.append(text + ("\n" if hard_break else " "))
            pos += len(text) + 1
        return "".join(out).rstrip(), starts


def line_at(starts: list[tuple[int, int]], pos: int) -> int:
    line = starts[0][1]
    for start, lineno in starts:
        if start > pos:
            break
        line = lineno
    return line


def sentences(text: str) -> list[tuple[int, str]]:
    pieces, last = [], 0
    for match in BOUNDARY.finditer(text):
        pieces.append((last, text[last:match.start()]))
        last = match.end()
    pieces.append((last, text[last:]))
    merged: list[tuple[int, str]] = []
    for start, piece in pieces:
        if merged and ABBREVIATION.search(merged[-1][1].rstrip("\"')] ")):
            merged[-1] = (merged[-1][0], merged[-1][1] + " " + piece)
        else:
            merged.append((start, piece))
    return [(start, piece.strip()) for start, piece in merged if count_words(piece)]


def parse(text: str) -> list[Unit]:
    lines = text.split("\n")
    units: list[Unit] = []
    current: Unit | None = None
    fence = None
    off = False
    i = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                i = j + 1
                break

    def flush() -> None:
        nonlocal current
        if current and current.parts:
            units.append(current)
        current = None

    while i < len(lines):
        raw, lineno = lines[i], i + 1
        i += 1
        fenced = FENCE.match(raw)
        if fence:
            if fenced and fenced.group(1)[0] == fence[0] and len(fenced.group(1)) >= len(fence):
                fence = None
            continue
        if fenced:
            flush()
            fence = fenced.group(1)
            continue
        switch = SWITCH.search(raw)
        if switch:
            flush()
            off = switch.group(1).lower() == "off"
            continue
        if off:
            continue
        if not raw.strip() or RULE_LINE.match(raw):
            flush()
            continue
        if re.match(r"^\s{0,3}>", raw):
            flush()
            continue
        heading = HEADING.match(raw)
        if heading:
            flush()
            unit = Unit("heading")
            unit.add(lineno, heading.group(1))
            if unit.parts:
                units.append(unit)
            continue
        if TABLE_ROW.match(raw):
            flush()
            rows = [(lineno, raw)]
            while i < len(lines) and (TABLE_ROW.match(lines[i]) or TABLE_SEP.match(lines[i])) and lines[i].strip():
                rows.append((i + 1, lines[i]))
                i += 1
            headers: list[str] = []
            body = rows
            if len(rows) > 1 and TABLE_SEP.match(rows[1][1]):
                headers = [clean(c) for c in split_row(rows[0][1])]
                body = rows[2:]
            for row_line, row in body:
                if TABLE_SEP.match(row):
                    continue
                for col, cell in enumerate(split_row(row)):
                    unit = Unit("cell", headers[col] if col < len(headers) else "")
                    unit.add(row_line, cell)
                    if unit.parts:
                        units.append(unit)
            continue
        numbered, bullet = NUMBERED.match(raw), BULLET.match(raw)
        if numbered or bullet:
            flush()
            current = Unit("step" if numbered else "item")
            current.add(lineno, (numbered or bullet).group(1))
            continue
        if current is None:
            current = Unit("para")
        current.add(lineno, raw.strip() + ("  " if raw.endswith("  ") else ""))
    flush()
    return units


def split_row(row: str) -> list[str]:
    inner = TABLE_ROW.match(row)
    body = inner.group(1) if inner else row.strip().strip("|")
    masked = re.sub(r"`[^`]*`", lambda m: m.group(0).replace("|", "\x00"), body).replace("\\|", "\x00")
    return [cell.replace("\x00", "|").strip() for cell in masked.split("|")]


class Glossary:
    def __init__(self) -> None:
        self.names: list[tuple[str, list[str]]] = []
        self.verbs: set[str] = set()
        self._allowed: re.Pattern | None = None
        self._banned: list[tuple[re.Pattern, str, str]] = []

    @staticmethod
    def _phrase(phrase: str) -> str:
        words = [re.escape(w) for w in phrase.split()]
        return r"(?<![\w-])" + r"\s+".join(words) + r"(?:s|es)?(?![\w-])"

    @classmethod
    def load(cls, text: str) -> "Glossary":
        glossary = cls()
        section = ""
        not_col = None
        fence = None
        for raw in text.split("\n"):
            fenced = FENCE.match(raw)
            if fenced and (fence is None or fenced.group(1)[0] == fence):
                fence = None if fence else fenced.group(1)[0]
                continue
            if fence:
                continue
            heading = HEADING.match(raw)
            if heading:
                title = heading.group(1).lower()
                section = "names" if re.search(r"\b(names?|terms?)\b", title) else "verbs" if "verb" in title else ""
                not_col = None
                continue
            if section == "names" and TABLE_ROW.match(raw) and not TABLE_SEP.match(raw):
                cells = [re.sub(r"[`*]", "", c).strip() for c in split_row(raw)]
                if not_col is None:
                    not_col = next((n for n, c in enumerate(cells) if NOT_HEADER.match(c)), -1)
                    continue
                use = cells[0] if cells else ""
                banned = []
                if 0 <= not_col < len(cells):
                    banned = [b.strip() for b in cells[not_col].split(",") if re.search(r"\w", b)]
                if use:
                    glossary.names.append((use, banned))
            elif section == "verbs" and VERB_LINE.match(raw):
                # only a bare list counts: "add, remove" or "- add". A sentence in the section is not a list.
                glossary.verbs.update(re.findall(r"[a-z]+", raw))
        allowed = sorted((use for use, _ in glossary.names), key=len, reverse=True)
        if allowed:
            glossary._allowed = re.compile("|".join(cls._phrase(a) for a in allowed), re.I)
        for use, banned in glossary.names:
            for phrase in banned:
                glossary._banned.append((re.compile(cls._phrase(phrase), re.I), phrase, use))
        return glossary

    def banned_terms(self, text: str) -> list[tuple[int, str, str]]:
        if not self._banned:
            return []
        masked = self._allowed.sub(lambda m: "\x00" * len(m.group(0)), text) if self._allowed else text
        spans = []
        for pattern, phrase, use in self._banned:
            for match in pattern.finditer(masked):
                spans.append((match.start(), match.end(), match.group(0), use))
        # "AP device ID" contains "device ID" and "device": report the longest phrase only
        hits = []
        for start, end, found, use in spans:
            inside = any(s <= start and end <= e and (e - s) > (end - start) for s, e, _, _ in spans)
            if not inside:
                hits.append((start, found, use))
        return sorted(set(hits))


def first_verb(sentence: str) -> str:
    words = sentence.split()
    if words and words[0].lower().strip(",") in LEAD_IN and "," in sentence:
        words = sentence.split(",", 1)[1].split()
    while words and words[0].lower().strip(",") == "then":
        words = words[1:]
    if len(words) >= 3 and [w.lower() for w in words[:2]] == ["do", "not"]:
        words = words[2:]
    return re.sub(r"[^\w-]", "", words[0]).lower() if words else ""


def lint(text: str, glossary: Glossary | None = None, filename: str = "<stdin>") -> list[dict]:
    glossary = glossary or Glossary()
    findings: list[dict] = []

    def add(line: int, level: str, rule: str, message: str, snippet: str) -> None:
        snippet = " ".join(snippet.split())
        if len(snippet) > 90:
            snippet = snippet[:87] + "..."
        findings.append({"file": filename, "line": line, "level": level, "rule": rule,
                         "message": message, "text": snippet})

    for unit in parse(text):
        body, starts = unit.joined()
        if not body:
            continue
        if unit.kind == "cell" and NOT_HEADER.match(unit.header):
            continue  # the column that lists the banned names is data, not prose
        for pos, found, use in glossary.banned_terms(body):
            add(line_at(starts, pos), "error", "term", "use \"%s\"" % use, found)
        if unit.kind == "heading":
            continue
        parts = sentences(body)
        limit = STEP_LIMIT if unit.kind == "step" else SENTENCE_LIMIT
        rule = "step-length" if unit.kind == "step" else "sentence-length"
        for pos, sentence in parts:
            words = count_words(sentence)
            if words > limit:
                add(line_at(starts, pos), "error", rule, "%d words, the limit is %d" % (words, limit), sentence)
        if unit.kind == "para" and len(parts) > PARAGRAPH_LIMIT:
            add(unit.parts[0][0], "error", "paragraph-length",
                "%d sentences, the limit is %d" % (len(parts), PARAGRAPH_LIMIT), parts[0][1])
        if unit.kind == "cell" and count_words(body) > CELL_LIMIT:
            add(unit.parts[0][0], "error", "cell-length",
                "%d words in one table cell, the limit is %d" % (count_words(body), CELL_LIMIT), body)
        seen: set[tuple[str, int]] = set()
        for name, level, pattern, message in RULES:
            for match in pattern.finditer(body):
                if (name, match.start()) in seen:
                    continue
                seen.add((name, match.start()))
                add(line_at(starts, match.start()), level, name, message, match.group(0))
        for match in PAREN.finditer(body):
            if count_words(match.group(1)) > PAREN_LIMIT:
                add(line_at(starts, match.start()), "warning", "parenthesis",
                    "long text in parentheses: write a sentence", match.group(0))
        if unit.kind == "step" and parts:
            pos, sentence = parts[0]
            cond = TRAILING_COND.search(sentence)
            if cond and sentence.split()[0].lower().strip(",") not in LEAD_IN:
                add(line_at(starts, pos), "warning", "trailing-condition",
                    "put the condition first: \"If X, do Y.\"", sentence)
            if glossary.verbs:
                verb = first_verb(sentence)
                if verb and verb not in glossary.verbs:
                    add(line_at(starts, pos), "error", "step-verb",
                        "a step starts with a verb from the glossary, not \"%s\". "
                        "If the reader does not do this, write a paragraph, not a numbered item" % verb, sentence)
    findings.sort(key=lambda f: (f["line"], f["level"], f["rule"]))
    return findings


def find_glossary(path: Path, explicit: str | None) -> Glossary:
    if explicit:
        return Glossary.load(Path(explicit).read_text(encoding="utf-8"))
    for name in ("GLOSSARY.md", "glossary.md"):
        candidate = path.parent / name
        if candidate.is_file():
            return Glossary.load(candidate.read_text(encoding="utf-8"))
    return Glossary.load(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint Markdown against the plain-docs writing rules.")
    parser.add_argument("paths", nargs="+", help="Markdown files or directories")
    parser.add_argument("--glossary", help="glossary file (default: GLOSSARY.md next to the file, else the file itself)")
    parser.add_argument("--strict", action="store_true", help="warnings also fail the run")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    args = parser.parse_args(argv)
    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            files += sorted(p for p in path.rglob("*.md") if p.is_file())
        elif path.is_file():
            files.append(path)
        else:
            print("%s: no such file" % raw, file=sys.stderr)
            return 2
    findings: list[dict] = []
    for path in files:
        findings += lint(path.read_text(encoding="utf-8"), find_glossary(path, args.glossary), str(path))
    errors = sum(1 for f in findings if f["level"] == "error")
    warnings = len(findings) - errors
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "findings": findings}, indent=2))
    else:
        for f in findings:
            print("%(file)s:%(line)d: %(level)s [%(rule)s] %(message)s: \"%(text)s\"" % f)
    print("%d error(s), %d warning(s) in %d file(s)" % (errors, warnings, len(files)), file=sys.stderr)
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
