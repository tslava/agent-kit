"""Tests for plugins/tech-writing/skills/plain-docs/scripts/fact_check.py."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/tech-writing/skills/plain-docs/scripts/fact_check.py"
spec = importlib.util.spec_from_file_location("fact_check", SCRIPT)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

SOURCE = """\
# 4.3 Update

The node retries each chunk up to 3 times; the limit is 30 minutes (see 4.1).
It writes 512 KiB chunks to `fw_slot_b` and validates the Ed25519 signature and the SHA-256.
On failure it reports `FAILED_VERIFY` over HTTP. Hub firmware older than 3.2 is not reliable.
"""


def tokens(rows):
    return [token for (_, token), _ in rows]


def test_identical_text_has_no_difference():
    assert fc.compare(SOURCE, SOURCE) == ([], [])


def test_missing_number_identifier_and_code_span():
    rewrite = "1. Retry each chunk 3 times.\n2. Write 512 KiB chunks.\n3. Validate the SHA-256.\nThe limit is 30 min. See 4.1. Hub 3.2. HTTP.\n"
    missing, _ = fc.compare(SOURCE, rewrite)
    assert tokens(missing) == ["fw_slot_b", "Ed25519", "FAILED_VERIFY"]


def test_unit_spelling_is_not_compared():
    missing, _ = fc.compare("The limit is 30 minutes.\n", "The limit is 30 min.\n")
    assert missing == []


def test_new_facts_in_the_rewrite_are_listed():
    rewrite = SOURCE + "\nCheck again every 5 minutes on `gh/status`.\n"
    missing, added = fc.compare(SOURCE, rewrite)
    assert missing == [] and tokens(added) == ["gh/status", "5"]


def test_list_numbers_heading_numbers_and_pointers_are_not_facts():
    rewrite = SOURCE + "\n## 7. Steps\n\n1. Do step 2 again.\n9) See section 8 and Q5.\n"
    assert fc.compare(SOURCE, rewrite)[1] == []


def test_number_inside_a_larger_number_or_name_does_not_match():
    missing, _ = fc.compare("Wait 3 seconds.\n", "Wait 30 seconds for SHA-3 and 1.3.\n")
    assert tokens(missing) == ["3"]


def test_code_span_matches_the_same_text_outside_backticks():
    missing, _ = fc.compare("Report `ROLLED_BACK`.\n", "Report ROLLED_BACK.\n")
    assert missing == []


def test_glossary_file_counts_as_part_of_the_rewrite(tmp_path, capsys):
    (tmp_path / "s.md").write_text("Use the Ed25519 key within 120 s.\n")
    (tmp_path / "r.md").write_text("Use the vendor key within 120 s.\n")
    (tmp_path / "g.md").write_text("| vendor key | | The Ed25519 key. |\n")
    assert fc.main([str(tmp_path / "s.md"), str(tmp_path / "r.md")]) == 1
    assert "Ed25519" in capsys.readouterr().out
    assert fc.main([str(tmp_path / "s.md"), str(tmp_path / "r.md"), str(tmp_path / "g.md")]) == 0
    assert fc.main([str(tmp_path / "s.md")]) == 2
    capsys.readouterr()
