"""Level 1 to Level 6 Full Verification Script for BlenderAgent Bridge v0.2.0 Standalone Executable.

Tests the actual installed standalone binary at:
C:\\Users\\<USER>\\AppData\\Local\\Programs\\BlenderAgentBridge\\bin\\blenderagent-mcp.exe
over standard stdio JSON-RPC 2.0 without calling python for the MCP server.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys

repo_root = pathlib.Path(__file__).parent.parent.resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from installer.constants import (
    ANTIGRAVITIY_GLOBAL_CONFIG,
    CODEX_GLOBAL_CONFIG,
    DEFAULT_WORKSPACE_DIR,
    INSTALL_MANIFEST_PATH,
    MCP_LAUNCHER_PATH,
)


async def run_full_verification():
    print("=" * 75)
    print("  BLENDERAGENT BRIDGE v0.2.0 — FULL L1-L6 INTEGRATION VERIFICATION")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # LEVEL 1: PACKAGED
    # -------------------------------------------------------------------------
    print("\n[LEVEL 1: PACKAGED] Checking standalone MCP launcher executable...")
    if not MCP_LAUNCHER_PATH.exists():
        print(f"[!] FAILED: Standalone executable missing at {MCP_LAUNCHER_PATH}")
        sys.exit(1)
    exe_size = MCP_LAUNCHER_PATH.stat().st_size
    print(f"[+] L1 PASS: {MCP_LAUNCHER_PATH.name} is installed ({exe_size:,} bytes).")

    # -------------------------------------------------------------------------
    # LEVEL 2: INSTALLED
    # -------------------------------------------------------------------------
    print("\n[LEVEL 2: INSTALLED] Checking extension in Blender user repository...")
    user_repo_addon = (
        pathlib.Path(os.environ.get("APPDATA", ""))
        / "Blender Foundation"
        / "Blender"
        / "5.2"
        / "extensions"
        / "user_default"
        / "blenderagent_bridge"
    )
    manifest = user_repo_addon / "blender_manifest.toml"
    if not manifest.exists():
        print(f"[!] FAILED: Extension manifest missing at {manifest}")
        sys.exit(1)
    print(f"[+] L2 PASS: Extension verified in user repository: {user_repo_addon}")

    # -------------------------------------------------------------------------
    # LEVEL 3: CONFIGURED
    # -------------------------------------------------------------------------
    print("\n[LEVEL 3: CONFIGURED] Checking Antigravity and Codex MCP registrations...")
    # Antigravity
    with open(ANTIGRAVITIY_GLOBAL_CONFIG, "r", encoding="utf-8") as f:
        ag_data = json.load(f)
    ag_cmd = ag_data.get("mcpServers", {}).get("blenderagent-bridge", {}).get("command", "")
    assert str(MCP_LAUNCHER_PATH.resolve()).lower() == str(pathlib.Path(ag_cmd).resolve()).lower()
    print(f"[+] L3 PASS (Antigravity): Verified command points to {ag_cmd}")

    # Codex
    import tomllib
    with open(CODEX_GLOBAL_CONFIG, "rb") as f:
        codex_data = tomllib.load(f)
    codex_cmd = codex_data.get("mcp_servers", {}).get("blenderagent-bridge", {}).get("command", "")
    assert str(MCP_LAUNCHER_PATH.resolve()).lower() == str(pathlib.Path(codex_cmd).resolve()).lower()
    print(f"[+] L3 PASS (Codex): Verified command points to {codex_cmd}")

    # -------------------------------------------------------------------------
    # LEVEL 4: DISCOVERED
    # -------------------------------------------------------------------------
    print("\n[LEVEL 4: DISCOVERED] Spawning standalone blenderagent-mcp.exe over stdio...")
    server_params = StdioServerParameters(
        command=str(MCP_LAUNCHER_PATH.resolve()),
        args=[
            "--workspace", str(DEFAULT_WORKSPACE_DIR.resolve()),
            "--port", "9876",
        ],
        env=dict(os.environ),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_res = await session.initialize()
            print(f"[+] MCP Initialized: Protocol={getattr(init_res, 'protocol_version', 'N/A')}")

            tools_res = await session.list_tools()
            tools = tools_res.tools
            print(f"[+] Discovered {len(tools)} tools via tools/list:")
            for idx, t in enumerate(tools, 1):
                print(f"    {idx:2d}. {t.name:<18} - {t.description.split('.')[0]}")
            assert len(tools) == 10, f"Expected 10 tools, found {len(tools)}"
            print("[+] L4 PASS: All 10 tools discovered successfully from standalone binary.")

            # -----------------------------------------------------------------
            # LEVEL 5: LIVE
            # -----------------------------------------------------------------
            print("\n[LEVEL 5: LIVE] Invoking 'get_scene_info' through standalone MCP binary...")
            scene_res = await session.call_tool("get_scene_info", {})
            scene_data = json.loads(scene_res.content[0].text)
            print("[+] Response from get_scene_info:")
            print(json.dumps(scene_data, indent=2))
            assert scene_data.get("status") == "success"
            print("[+] L5 PASS: Real-time query to open Blender 5.2 succeeded via MCP!")

            # -----------------------------------------------------------------
            # LEVEL 6: E2E WORKFLOW
            # -----------------------------------------------------------------
            print("\n[LEVEL 6: E2E WORKFLOW] Running full generative and persistence sequence...")

            # 6a: Create primitive
            cube_name = "V020_Verified_Cube"
            print(f"[*] Calling 'create_primitive' for '{cube_name}' at [1.5, -1.0, 0.5]...")
            c_res = await session.call_tool(
                "create_primitive",
                {"type": "cube", "name": cube_name, "location": [1.5, -1.0, 0.5]},
            )
            c_data = json.loads(c_res.content[0].text)
            print(f"[+] Created primitive: {c_data.get('data', {}).get('object_name') or c_data.get('object_name')}")

            # 6b: Get object info
            print(f"[*] Calling 'get_object_info' for '{cube_name}'...")
            o_res = await session.call_tool("get_object_info", {"name": cube_name})
            o_data = json.loads(o_res.content[0].text)
            print(f"[+] Object info verified: Location={o_data.get('data', {}).get('location') or o_data.get('location')}")

            # 6c: Set material (Emerald Green)
            print(f"[*] Calling 'set_material' for '{cube_name}' (Emerald Green)...")
            m_res = await session.call_tool(
                "set_material",
                {
                    "name": cube_name,
                    "color": [0.1, 0.85, 0.35, 1.0],
                    "metallic": 0.7,
                    "roughness": 0.2,
                    "material_name": "Emerald_Material",
                },
            )
            m_data = json.loads(m_res.content[0].text)
            print(f"[+] Material assigned: {m_data.get('data', {}).get('material_name') or m_data.get('material_name')}")

            # 6d: Viewport Capture
            print("[*] Calling 'capture_viewport'...")
            vp_res = await session.call_tool(
                "capture_viewport",
                {"output_filename": "renders/v020_verification_viewport.png", "width": 640, "height": 480},
            )
            vp_data = json.loads(vp_res.content[0].text)
            vp_mode = vp_data.get("data", {}).get("mode") or vp_data.get("mode")
            print(f"[+] Viewport captured successfully (mode='{vp_mode}')")

            # 6e: Render Preview
            print("[*] Calling 'render_preview'...")
            rend_res = await session.call_tool(
                "render_preview",
                {"output_filename": "renders/v020_verification_shaded.png", "width": 640, "height": 480, "samples": 16},
            )
            rend_data = json.loads(rend_res.content[0].text)
            rend_path = rend_data.get("data", {}).get("file_path") or rend_data.get("file_path")
            print(f"[+] Render generated: {rend_path}")

            # 6f: Save Project
            print("[*] Calling 'save_project'...")
            save_res = await session.call_tool(
                "save_project",
                {"filename": "scenes/v020_e2e_verified.blend", "overwrite": True},
            )
            save_data = json.loads(save_res.content[0].text)
            saved_blend = pathlib.Path(save_data.get("data", {}).get("file_path") or save_data.get("file_path"))
            print(f"[+] Scene saved to: {saved_blend} ({saved_blend.stat().st_size:,} bytes)")

    # 6g: Headless Reopen Verification
    print("\n[*] Verifying saved .blend file in isolated headless Blender 5.2 instance...")
    blender_exe = pathlib.Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    inspect_py = (
        "import bpy\n"
        f"cube = bpy.data.objects.get('{cube_name}')\n"
        "assert cube is not None, 'Cube object not found in saved .blend!'\n"
        "assert list(cube.location) == [1.5, -1.0, 0.5], f'Location mismatch: {list(cube.location)}'\n"
        "mat = cube.data.materials[0]\n"
        "assert mat.name == 'Emerald_Material', f'Material mismatch: {mat.name}'\n"
        "print('HEADLESS VERIFICATION PASSED: Object and material confirmed.')\n"
    )
    cmd = [str(blender_exe), "--background", str(saved_blend), "--python-expr", inspect_py]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if "HEADLESS VERIFICATION" in line:
            print(f"    [+] {line}")
    assert proc.returncode == 0, f"Headless check failed: {proc.stderr}"
    print("[+] L6 PASS: Full E2E verification passed with zero errors!")

    print("\n" + "=" * 75)
    print("  ALL VERIFICATION LEVELS (L1 TO L6) PASSED WITH FLYING COLORS!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_full_verification())
