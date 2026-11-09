"""Tests for plugins/python-lambda/skills/dependency-cooldown/scripts/apply_cooldown.py."""
import importlib.util
import tomllib
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/python-lambda/skills/dependency-cooldown/scripts/apply_cooldown.py"
spec = importlib.util.spec_from_file_location("apply_cooldown", SCRIPT)
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)


def toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def test_poetry_creates_poetry_toml(tmp_path):
    (tmp_path / "poetry.lock").touch()
    action, target, note = ac.apply(str(tmp_path), 15, "auto")
    assert action == "created" and note == ""
    assert toml(Path(target))["solver"]["min-release-age"] == 15


def test_poetry_preserves_existing_sections(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "a"\n')
    (tmp_path / "poetry.toml").write_text("[virtualenvs]\nin-project = true\n")
    action, target, _ = ac.apply(str(tmp_path), 15, "auto")
    data = toml(Path(target))
    assert action == "updated"
    assert data["virtualenvs"]["in-project"] is True
    assert data["solver"]["min-release-age"] == 15


def test_uv_adds_exclude_newer(tmp_path):
    (tmp_path / "uv.lock").touch()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "u"\n')
    action, target, _ = ac.apply(str(tmp_path), 15, "auto")
    assert action == "updated"
    assert toml(Path(target))["tool"]["uv"]["exclude-newer"] == "15 days"


def test_uv_inserts_into_existing_tool_uv_table(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "u"\n\n[tool.uv]\npackage = false\n')
    ac.apply(str(tmp_path), 7, "auto")
    uv = toml(tmp_path / "pyproject.toml")["tool"]["uv"]
    assert uv == {"package": False, "exclude-newer": "7 days"}


def test_idempotent(tmp_path):
    (tmp_path / "poetry.lock").touch()
    ac.apply(str(tmp_path), 15, "auto")
    before = (tmp_path / "poetry.toml").read_text()
    action, _, note = ac.apply(str(tmp_path), 15, "auto")
    assert action == "already-set" and note == ""
    assert (tmp_path / "poetry.toml").read_text() == before


def test_different_value_is_left_alone_and_reported(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.uv]\nexclude-newer = "7 days"\n')
    action, target, note = ac.apply(str(tmp_path), 15, "auto")
    assert action == "already-set" and "7 days" in note
    assert toml(Path(target))["tool"]["uv"]["exclude-newer"] == "7 days"


def test_unknown_tool_changes_nothing(tmp_path):
    action, _, _ = ac.apply(str(tmp_path), 15, "auto")
    assert action == "unknown"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("tool,file", [("poetry", "poetry.toml"), ("uv", "pyproject.toml")])
def test_forced_tool(tmp_path, tool, file):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    action, target, _ = ac.apply(str(tmp_path), 10, tool)
    assert Path(target).name == file
