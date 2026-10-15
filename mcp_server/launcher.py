"""Standalone launcher entrypoint for compiling blenderagent-mcp.exe."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

# Ensure local imports work cleanly when frozen by PyInstaller
if getattr(sys, "frozen", False):
    base_dir = pathlib.Path(sys._MEIPASS)
else:
    base_dir = pathlib.Path(__file__).parent.parent

from mcp_server.client import BlenderBridgeClient
from mcp_server.server import create_mcp_server


def get_default_workspace() -> pathlib.Path:
    """Return default secure user-writable workspace directory."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        ws = pathlib.Path(local_appdata) / "BlenderAgentBridge" / "workspace"
    else:
        ws = pathlib.Path.home() / ".blenderagent" / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def main():
    parser = argparse.ArgumentParser(description="BlenderAgent Bridge Standalone MCP Server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BLENDERAGENT_PORT", 9876)))
    parser.add_argument("--token", type=str, default=os.environ.get("BLENDERAGENT_TOKEN", ""))
    parser.add_argument("--workspace", type=str, default="")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")

    args = parser.parse_args()

    if args.workspace:
        ws_path = pathlib.Path(args.workspace).resolve()
    else:
        ws_path = get_default_workspace()

    ws_path.mkdir(parents=True, exist_ok=True)

    client = BlenderBridgeClient(
        port=args.port,
        token=args.token or None,
        workspace_dir=ws_path,
    )

    # Automatically resolve token from session file if not passed via env/cli
    client._discover_session()

    server = create_mcp_server("blenderagent-bridge", client=client)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
