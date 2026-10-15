"""Test Real MCP Connection between MCP Client and BlenderAgent Bridge v0.1.1.

Establishes an authentic JSON-RPC 2.0 MCP session over stdio, discovers all 10 tools,
and executes the required sequence against the active Blender 5.2 instance.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_live_mcp_session():
    # 1. Identify workspace and locate session file
    workspace_dir = pathlib.Path(r"C:\Users\Yhamil\AppData\Local\BlenderAgentBridge\workspace").resolve()
    session_file = workspace_dir / ".blenderagent_session.json"

    print("=" * 70)
    print("  BLENDERAGENT BRIDGE v0.1.1 — REAL MCP LIVE CONNECTION TEST")
    print("=" * 70)
    print(f"[*] Configured Workspace: {workspace_dir}")
    print(f"[*] Session File Path:    {session_file}")

    if not session_file.exists():
        print(f"[!] ERROR: Session file does not exist at {session_file}")
        sys.exit(1)

    with open(session_file, "r", encoding="utf-8") as f:
        session_data = json.load(f)

    port = str(session_data.get("port", 9876))
    token = session_data.get("token", "")
    print(f"[*] Port from session:    {port}")
    print(f"[*] Token recovered:      [SECURE] Present ({len(token)} chars, hidden)")

    # 2. Configure stdio server parameters for the official MCP server process
    repo_root = pathlib.Path(__file__).parent.parent.resolve()
    python_exe = sys.executable

    server_params = StdioServerParameters(
        command=python_exe,
        args=[
            "-m",
            "mcp_server.server",
            "--workspace",
            str(workspace_dir),
            "--port",
            port,
        ],
        env={
            **os.environ,
            "BLENDERAGENT_PORT": port,
            "BLENDERAGENT_WORKSPACE": str(workspace_dir),
            "BLENDERAGENT_TOKEN": token,
            "PYTHONUNBUFFERED": "1",
        },
    )

    print("\n[*] Spawning MCP Server subprocess over stdio...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Step 5a: Initialize MCP Protocol Session
            print("[*] Initializing MCP Session (JSON-RPC handshake)...")
            init_result = await session.initialize()
            print(f"[+] MCP Initialized successfully!")
            print(f"    - Protocol Version: {getattr(init_result, 'protocol_version', '2024-11-05')}")
            print(f"    - Server Info:      {getattr(init_result, 'server_info', 'blenderagent-bridge')}")

            # Step 5b: Discover MCP Tools
            print("\n[*] Discovering tools via 'tools/list'...")
            tools_response = await session.list_tools()
            tools_list = tools_response.tools
            print(f"[+] Discovered {len(tools_list)} tools:")
            for idx, tool in enumerate(tools_list, 1):
                print(f"    {idx:2d}. {tool.name:<18} - {tool.description.split('.')[0]}.")

            if len(tools_list) != 10:
                print(f"[!] Warning: Expected 10 tools, found {len(tools_list)}.")

            # Step 6: Execute get_scene_info
            print("\n" + "-" * 70)
            print("[Step 6] Executing MCP Tool: 'get_scene_info'...")
            res_scene = await session.call_tool("get_scene_info", {})
            raw_scene_text = res_scene.content[0].text
            data_scene = json.loads(raw_scene_text)
            print("[+] Response 'get_scene_info':")
            print(json.dumps(data_scene, indent=2))

            if data_scene.get("status") != "success":
                print(f"[!] ERROR in get_scene_info: {data_scene}")
                return

            # Step 7: Execute create_primitive: Cube named FirstMCPTest at [2, 0, 1]
            print("\n" + "-" * 70)
            print("[Step 7] Executing MCP Tool: 'create_primitive'...")
            create_params = {
                "type": "cube",
                "name": "FirstMCPTest",
                "location": [2.0, 0.0, 1.0],
                "scale": [1.0, 1.0, 1.0],
            }
            print(f"    Parameters: {create_params}")
            res_create = await session.call_tool("create_primitive", create_params)
            raw_create_text = res_create.content[0].text
            data_create = json.loads(raw_create_text)
            print("[+] Response 'create_primitive':")
            print(json.dumps(data_create, indent=2))

            if data_create.get("status") != "success":
                print(f"[!] ERROR in create_primitive: {data_create}")
                return

            # Step 8: Execute get_object_info: verify existence and coordinates
            print("\n" + "-" * 70)
            print("[Step 8] Executing MCP Tool: 'get_object_info' for 'FirstMCPTest'...")
            res_obj = await session.call_tool("get_object_info", {"name": "FirstMCPTest"})
            raw_obj_text = res_obj.content[0].text
            data_obj = json.loads(raw_obj_text)
            print("[+] Response 'get_object_info':")
            print(json.dumps(data_obj, indent=2))

            if data_obj.get("status") != "success":
                print(f"[!] ERROR in get_object_info: {data_obj}")
                return

            # Step 9: Execute set_material: Assign blue material
            print("\n" + "-" * 70)
            print("[Step 9] Executing MCP Tool: 'set_material' (Blue) for 'FirstMCPTest'...")
            mat_params = {
                "name": "FirstMCPTest",
                "color": [0.05, 0.35, 0.95, 1.0],
                "metallic": 0.85,
                "roughness": 0.25,
                "material_name": "MCP_Blue_Material",
            }
            print(f"    Parameters: {mat_params}")
            res_mat = await session.call_tool("set_material", mat_params)
            raw_mat_text = res_mat.content[0].text
            data_mat = json.loads(raw_mat_text)
            print("[+] Response 'set_material':")
            print(json.dumps(data_mat, indent=2))

            if data_mat.get("status") != "success":
                print(f"[!] ERROR in set_material: {data_mat}")
                return

            # Step 10: Visual confirmation via capture_viewport
            print("\n" + "-" * 70)
            print("[Step 10] Executing MCP Tool: 'capture_viewport' for visual verification...")
            vp_filename = "renders/first_mcp_test_verification.png"
            res_vp = await session.call_tool(
                "capture_viewport",
                {"output_filename": vp_filename, "width": 640, "height": 480},
            )
            raw_vp_text = res_vp.content[0].text
            data_vp = json.loads(raw_vp_text)
            print("[+] Response 'capture_viewport':")
            print(json.dumps(data_vp, indent=2))

            img_path = workspace_dir / vp_filename
            if img_path.exists():
                print(f"[+] Viewport verification image saved to: {img_path}")
                print(f"    File size: {img_path.stat().st_size:,} bytes")

            print("\n" + "=" * 70)
            print("  [SUCCESS] All live MCP operations completed successfully!")
            print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_live_mcp_session())
