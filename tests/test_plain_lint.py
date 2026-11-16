"""Tests for plugins/tech-writing/skills/plain-docs/scripts/plain_lint.py."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/tech-writing/skills/plain-docs/scripts/plain_lint.py"
spec = importlib.util.spec_from_file_location("plain_lint", SCRIPT)
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)

GLOSSARY = """\
# Glossary

## Names

| Use | Not | Meaning |
|---|---|---|
| node | unit, field controller | The box in the field that opens one valve. |
| firmware image | image, bundle | The file that the hub sends to a node. |

## Verbs

add, remove, read, write, send, erase, test, make
"""


def rules(text, glossary=None, level=None):
    found = pl.lint(text, pl.Glossary.load(glossary) if glossary else None)
    return [f["rule"] for f in found if level is None or f["level"] == level]


def words(n):
    return " ".join(["word"] * n)


def test_clean_text_has_no_findings():
    text = "The hub reads the node ID. Then it sends the ID to the server.\n\n1. Erase the flash.\n2. If the read fails, stop.\n"
    assert rules(text) == []


def test_step_limit_is_20_and_description_limit_is_25():
    assert rules("1. Erase " + words(20) + ".\n") == ["step-length"]
    assert rules("1. Erase " + words(19) + ".\n") == []
    assert rules("The node " + words(24) + ".\n") == ["sentence-length"]
    assert rules("- The node " + words(23) + ".\n") == []


def test_code_and_urls_count_as_one_word_each():
    step = "1. Run `fwtool load --verify --execute build/app.bin --offset 0x10000000 -f` now and read " + words(12) + ".\n"
    assert rules(step) == []


def test_paragraph_of_seven_sentences_fails():
    assert rules(" ".join(["The node starts."] * 7) + "\n") == ["paragraph-length"]
    assert rules(" ".join(["The node starts."] * 6) + "\n") == []


def test_table_cell_limit_and_cell_rules():
    table = "| Part | Role |\n|---|---|\n| Valve | " + words(26) + " |\n"
    found = rules(table)
    assert "cell-length" in found
    assert rules("| Part | Role |\n|---|---|\n| Valve | You should restart it. |\n") == ["modal"]


def test_header_row_and_pipes_inside_code_are_not_split():
    table = "| Part | Role |\n|---|---|\n| `a | b` | Reads the key. |\n"
    assert rules(table) == []


def test_mechanical_errors():
    assert rules("The hub rejects it; the node waits.\n") == ["semicolon"]
    assert rules("The hub rejects it — the node waits.\n") == ["dash"]
    assert rules("The hub doesn't answer.\n") == ["contraction"]
    assert rules("The key has been erased.\n", level="error") == ["perfect-tense"]
    assert rules("The device could reboot.\n") == ["modal"]
    assert rules("Use a tool, e.g. the hub.\n") == ["latin"]


def test_may_the_month_is_not_a_modal():
    assert rules("The visit is in May 2027.\n") == []


def test_warnings_do_not_count_as_errors():
    text = "The image is signed by the pipeline, making it safe.\n"
    assert rules(text, level="error") == []
    assert set(rules(text, level="warning")) == {"passive", "ing-clause"}


def test_nominalization_and_filler_warn():
    assert rules("Perform testing of the valve.\n") == ["nominalization"]
    assert rules("Do nothing.\n") == []
    assert rules("Simply restart the service.\n") == ["filler"]


def test_code_blocks_quotes_and_front_matter_are_skipped():
    text = "---\ntitle: it's; fine\n---\n\n```\nit's; could\n```\n\n> The source said: it's; could.\n\nThe node starts.\n"
    assert rules(text) == []


def test_lint_off_and_on():
    text = "<!-- plain-lint: off -->\nIt's quoted; could.\n<!-- plain-lint: on -->\n\nIt's not.\n"
    assert rules(text) == ["contraction"]


def test_banned_term_from_glossary():
    found = pl.lint("The unit starts.\n", pl.Glossary.load(GLOSSARY))
    assert [(f["rule"], f["text"], f["message"]) for f in found] == [("term", "unit", 'use "node"')]


def test_allowed_term_hides_the_banned_word_inside_it():
    assert rules("Write the firmware image to the node.\n", GLOSSARY) == []
    assert rules("Write the image to the node.\n", GLOSSARY) == ["term"]


def test_banned_plural_and_two_word_term():
    assert rules("Two units start.\n", GLOSSARY) == ["term"]
    assert rules("The field controller starts.\n", GLOSSARY) == ["term"]


def test_banned_term_in_code_is_ignored():
    assert rules("Set `unit_id` on the node.\n", GLOSSARY) == []


def test_heading_is_checked_for_terms_only():
    assert rules("## Why the unit could fail; a note\n", GLOSSARY) == ["term"]


def test_glossary_table_may_list_its_own_banned_words():
    assert rules(GLOSSARY, GLOSSARY) == []


def test_step_must_start_with_a_glossary_verb():
    assert rules("1. Erase the flash.\n", GLOSSARY) == []
    assert rules("1. Flash the node.\n", GLOSSARY) == ["step-verb"]
    assert rules("1. If the read fails, erase the flash.\n", GLOSSARY) == []
    assert rules("1. Do not erase the slot.\n", GLOSSARY) == []
    assert rules("1. Then send the ID.\n", GLOSSARY) == []
    assert rules("1. The hub erases the flash.\n", GLOSSARY) == ["step-verb"]


def test_no_verb_list_means_no_verb_check():
    assert rules("1. Flash the node.\n") == []


def test_trailing_condition_warns_in_steps_only():
    assert rules("1. Stop if the read fails.\n") == ["trailing-condition"]
    assert rules("The hub stops if the read fails.\n") == []


def test_line_numbers_point_at_the_source_line():
    text = "The node starts.\n\nThe hub\nrejects it; the node\nwaits.\n"
    found = pl.lint(text)
    assert [(f["rule"], f["line"]) for f in found] == [("semicolon", 4)]


def test_abbreviation_does_not_end_a_sentence():
    assert len(pl.sentences("Use v2 vs. Version 3 here. Then stop.")) == 2


def test_cli_exit_codes(tmp_path, capsys):
    good, bad, warn = tmp_path / "good.md", tmp_path / "bad.md", tmp_path / "warn.md"
    good.write_text("The node starts.\n")
    bad.write_text("The node doesn't start.\n")
    warn.write_text("The image is signed.\n")
    assert pl.main([str(good)]) == 0
    assert pl.main([str(bad)]) == 1
    assert pl.main([str(warn)]) == 0
    assert pl.main([str(warn), "--strict"]) == 1
    assert pl.main([str(tmp_path / "missing.md")]) == 2
    capsys.readouterr()


def test_cli_finds_glossary_next_to_the_file(tmp_path, capsys):
    (tmp_path / "GLOSSARY.md").write_text(GLOSSARY)
    doc = tmp_path / "plan.md"
    doc.write_text("The unit starts.\n")
    assert pl.main([str(tmp_path)]) == 1
    assert "use \"node\"" in capsys.readouterr().out


def test_glossary_loader_skips_code_blocks():
    text = "## Names\n\n```markdown\n| Use | Not | Meaning |\n|---|---|---|\n| node | unit | An example. |\n```\n\nThe unit starts.\n"
    assert rules(text, text) == []


def test_verbs_come_from_the_list_only_not_from_a_sentence():
    glossary = pl.Glossary.load("## Verbs\n\nA task starts with one of these verbs.\n\nadd, remove,\n- test\n")
    assert glossary.verbs == {"add", "remove", "test"}


def test_overlapping_bans_report_the_longest_phrase_only():
    glossary = "## Names\n\n| Use | Not |\n|---|---|\n| node | device |\n| `node_id` | device ID |\n| remote device ID | AP device ID |\n"
    found = pl.lint("The AP device ID changed.\n", pl.Glossary.load(glossary))
    assert [(f["text"], f["message"]) for f in found] == [("AP device ID", 'use "remote device ID"')]


def test_the_not_column_is_data_and_is_not_linted():
    table = "## Names\n\n| Use | Not | Meaning |\n|---|---|---|\n| operator | installer, field engineer | The person; who should run it. |\n"
    assert sorted(rules(table, table)) == ["modal", "semicolon"]
