from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes.mcp.setup import main


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
