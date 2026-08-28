"""Wire an MCP assistant to HERMES by writing a ``.mcp.json`` in this folder.

The installed HERMES ships the ``hermes-mcp`` server command. To use it, an
assistant like Claude Code reads a ``.mcp.json`` in the project folder that
tells it how to launch the server. Rather than copying that file by hand, a
user runs this command once from their analysis folder:

    pixi run hermes-mcp-setup

It writes (or updates) ``.mcp.json`` in the current folder with the HERMES
server entry, keeping any other servers the file already lists.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

# How an assistant launches the bundled server: run it through pixi so it uses
# the HERMES installed in this folder's environment.
HERMES_SERVER = {"command": "pixi", "args": ["run", "hermes-mcp"]}


def main() -> None:
    config_path = Path.cwd() / ".mcp.json"

    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        try:
            config = json.loads(text)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"{config_path} exists but is not valid JSON; fix or remove it "
                f"first: {error}"
            )
        if not isinstance(config, dict):
            raise SystemExit(
                f"{config_path} exists but is not a JSON object; fix or remove "
                f"it first."
            )
        servers = config.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise SystemExit(
                f'{config_path} has a non-object "mcpServers"; fix or remove it '
                f"first."
            )
    else:
        config = {"mcpServers": {}}
        servers = config["mcpServers"]

    servers["hermes"] = HERMES_SERVER
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    logger.bind(domain="mcp").info(
        "wrote hermes MCP server entry to {path}", path=str(config_path)
    )
    print(
        f"Wrote the hermes MCP server to {config_path}. "
        f"Restart your assistant to pick it up."
    )
