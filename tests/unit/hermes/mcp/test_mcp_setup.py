from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes.mcp.setup import SKILLS_DIRECTORY, main


def test_writes_a_new_mcp_json_with_the_hermes_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    main()

    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert config == {
        "mcpServers": {
            "hermes": {"command": "pixi", "args": ["run", "hermes-mcp"]}
        }
    }


def test_merges_into_an_existing_file_and_keeps_other_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "run-other"}}}),
        encoding="utf-8",
    )

    main()

    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["other"] == {"command": "run-other"}
    assert config["mcpServers"]["hermes"] == {
        "command": "pixi",
        "args": ["run", "hermes-mcp"],
    }


def test_running_twice_leaves_one_valid_hermes_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    main()
    main()

    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert list(config["mcpServers"]) == ["hermes"]


def test_invalid_existing_json_is_reported_and_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    broken = "{ not valid json"
    (tmp_path / ".mcp.json").write_text(broken, encoding="utf-8")

    with pytest.raises(SystemExit, match="not valid JSON"):
        main()

    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == broken


def test_copies_the_hermes_skills_and_leaves_other_skills_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    skills = tmp_path / ".claude" / "skills"
    (skills / "other-skill").mkdir(parents=True)
    (skills / "other-skill" / "SKILL.md").write_text("mine", encoding="utf-8")
    # An older copy of a HERMES skill, with a file the new copy no longer has.
    old_copy = skills / "hermes-config-and-files"
    old_copy.mkdir()
    (old_copy / "old_guide.md").write_text("old", encoding="utf-8")

    main()

    shipped = SKILLS_DIRECTORY / "hermes-config-and-files"
    assert (old_copy / "SKILL.md").read_text(encoding="utf-8") == (
        shipped / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert (old_copy / "output_files.md").is_file()
    assert (old_copy / "scripts" / "show_config_fields.py").is_file()
    assert not (old_copy / "old_guide.md").exists()
    assert (skills / "other-skill" / "SKILL.md").read_text(encoding="utf-8") == "mine"
