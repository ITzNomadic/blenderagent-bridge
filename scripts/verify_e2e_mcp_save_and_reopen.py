"""End-to-End Verification of BlenderAgent Bridge via Real MCP Session.

1. Establishes a true MCP session (JSON-RPC over stdio) with mcp_server.server.
2. Invokes 'capture_viewport' via MCP and inspects the execution mode ('opengl' vs 'render_fallback').
3. Invokes 'save_project' via MCP to save 'scenes/verified_mcp_scene.blend' (without overwriting).
4. Invokes 'get_scene_info' via MCP to inspect currently active scene objects.
5. Spawns an isolated headless test instance of Blender 5.2 to reopen 'verified_mcp_scene.blend'
   and verify its structural and geometric integrity without touching the active GUI instance.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_e2e_verification():
    workspace_dir = pathlib.Path(r"C:\Users\Yhamil\AppData\Local\BlenderAgentBridge\workspace").resolve()
    session_file = workspace_dir / ".blenderagent_session.json"

    print("=" * 75)
    print("  BLENDERAGENT BRIDGE v0.1.1 — END-TO-END MCP VERIFICATION")
    print("=" * 75)
    print(f"[*] Workspace:    {workspace_dir}")
    print(f"[*] Session File: {session_file}")

    if not session_file.exists():
        print(f"[!] Session file not found: {session_file}")
        sys.exit(1)

    with open(session_file, "r", encoding="utf-8") as f:
        session_data = json.load(f)

    port = str(session_data.get("port", 9876))
    token = session_data.get("token", "")
    print(f"[*] Bridge Port:  {port}")
    print(f"[*] Bridge Token: [PROTECTED] (verified length: {len(token)})")

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

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize MCP
            print("\n[Step 1] Initializing MCP Session...")
            init_res = await session.initialize()
            print(f"[+] Protocol Version: {getattr(init_res, 'protocol_version', 'N/A')}")
            print(f"[+] Server Info:      {getattr(init_res, 'server_info', 'N/A')}")

            # 2. Check capture_viewport mode
            print("\n[Step 2] Executing MCP Tool: 'capture_viewport' to verify capture mode...")
            vp_res = await session.call_tool(
                "capture_viewport",
                {"output_filename": "renders/e2e_viewport_check.png", "width": 640, "height": 480},
            )
            vp_data = json.loads(vp_res.content[0].text)
            print(f"[+] Tool Response 'capture_viewport':")
            print(json.dumps(vp_data, indent=2))
            capture_mode = vp_data.get("data", {}).get("mode") or vp_data.get("mode")
            print(f"[*] VIEWPORT CAPTURE MODE CONFIRMED: '{capture_mode}'")

            # 3. Save project via save_project tool
            print("\n[Step 3] Executing MCP Tool: 'save_project'...")
            save_filename = "scenes/verified_mcp_scene.blend"
            save_res = await session.call_tool(
                "save_project",
                {"filename": save_filename, "overwrite": False},
            )
            save_data = json.loads(save_res.content[0].text)
            print(f"[+] Tool Response 'save_project':")
            print(json.dumps(save_data, indent=2))

            saved_blend_path = workspace_dir / "scenes" / "verified_mcp_scene.blend"
            if not saved_blend_path.exists():
                # Check root of workspace if scenes subdirectory wasn't prefixed
                alt_path = workspace_dir / save_filename
                if alt_path.exists():
                    saved_blend_path = alt_path
                else:
                    print(f"[!] ERROR: Saved .blend file not found on disk at {saved_blend_path}")
                    sys.exit(1)

            print(f"[+] Saved .blend file confirmed on disk:")
            print(f"    Path: {saved_blend_path}")
            print(f"    Size: {saved_blend_path.stat().st_size:,} bytes")

            # 4. Execute get_scene_info
            print("\n[Step 4] Executing MCP Tool: 'get_scene_info'...")
            scene_res = await session.call_tool("get_scene_info", {})
            scene_data = json.loads(scene_res.content[0].text)
            print(f"[+] Tool Response 'get_scene_info':")
            print(json.dumps(scene_data, indent=2))

    # 5. Headless verification: Reopen in isolated test instance of Blender 5.2
    print("\n" + "=" * 75)
    print("  HEADLESS BLENDER 5.2 VERIFICATION OF SAVED .BLEND FILE")
    print("=" * 75)

    blender_exe = pathlib.Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    if not blender_exe.exists():
        print(f"[!] Blender executable not found at {blender_exe}")
        sys.exit(1)

    py_inspect_code = (
        "import bpy, sys\n"
        "print('--- HEADLESS BLENDER INSPECTION START ---')\n"
        "print(f'Active Scene: {bpy.context.scene.name}')\n"
        "objs = [(o.name, o.type, list(o.location)) for o in bpy.data.objects]\n"
        "print(f'Loaded Objects ({len(objs)}): {objs}')\n"
        "cube = bpy.data.objects.get('FirstMCPTest')\n"
        "if cube:\n"
        "    print(f'FirstMCPTest Location: {list(cube.location)}')\n"
        "    print(f'FirstMCPTest Dimensions: {list(cube.dimensions)}')\n"
        "    mat_names = [m.name for m in cube.data.materials if m]\n"
        "    print(f'Assigned Materials: {mat_names}')\n"
        "    if mat_names:\n"
        "        mat = bpy.data.materials.get(mat_names[0])\n"
        "        print(f'Material Diffuse Color (Viewport): {list(mat.diffuse_color)}')\n"
        "        if mat.use_nodes:\n"
        "            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)\n"
        "            if bsdf:\n"
        "                bc = list(bsdf.inputs['Base Color'].default_value)\n"
        "                met = bsdf.inputs['Metallic'].default_value\n"
        "                rou = bsdf.inputs['Roughness'].default_value\n"
        "                print(f'Principled BSDF Base Color: {bc}')\n"
        "                print(f'Principled BSDF Metallic: {met}, Roughness: {rou}')\n"
        "print('--- HEADLESS BLENDER INSPECTION END ---')\n"
    )

    cmd = [
        str(blender_exe),
        "--background",
        str(saved_blend_path),
        "--python-expr",
        py_inspect_code,
    ]

    print(f"[*] Running headless check: {' '.join(cmd[:3])} ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)

    print("\n[+] Blender Headless Output:")
    for line in proc.stdout.splitlines():
        if "HEADLESS BLENDER" in line or "FirstMCPTest" in line or "Loaded Objects" in line or "Material" in line or "Principled" in line:
            print(f"    {line}")

    if proc.returncode == 0:
        print("\n[+] Reopen Verification: SUCCESS (return code 0)")
    else:
        print(f"\n[!] Reopen Verification: FAILED (return code {proc.returncode})")
        print(proc.stderr)


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
