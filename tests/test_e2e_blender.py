"""End-to-End Functional Test against a live, running instance of Blender 5.2 / 4.5.

Executes the Phase 5 12-step validation flow:
1. Start Blender with addon.
2. Start BlenderAgent Bridge.
3. Connect MCP client.
4. get_scene_info.
5. create_primitive 'AgentCube'.
6. transform_object to (2, 0, 1).
7. set_material metallic blue.
8. set_camera & basic lighting.
9. render_preview.
10. save_project as 'blenderagent_demo.blend'.
11. get_object_info and verify properties.
12. Verify file persisted and Blender remains responsive.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import time
import httpx
import pytest

from mcp_server.client import BlenderBridgeClient
from mcp_server.server import create_mcp_server

BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"


@pytest.mark.skipif(not os.path.exists(BLENDER_EXE), reason="Blender executable not found at specified path.")
def test_full_phase5_e2e_flow(temp_workspace):
    port = 9892
    token = "e2e_secret_token_12345"
    repo_root = pathlib.Path(__file__).parent.parent.resolve()
    runner_script = repo_root / "scripts" / "run_blender_bridge.py"

    # 1. Launch Blender in background
    cmd = [
        BLENDER_EXE,
        "-b",
        "-P",
        str(runner_script),
        "--",
        "--port",
        str(port),
        "--token",
        token,
        "--workspace",
        str(temp_workspace),
        "--duration",
        "45",  # 45 seconds total window for test
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(repo_root),
        text=True,
    )

    try:
        # 2. Wait for bridge server to respond on 127.0.0.1:<port>
        health_url = f"http://127.0.0.1:{port}/api/v1/health"
        bridge_alive = False
        start_wait = time.time()
        while time.time() - start_wait < 15.0:
            try:
                with httpx.Client(timeout=1.0) as client:
                    res = client.get(health_url)
                    if res.status_code == 200:
                        bridge_alive = True
                        break
            except Exception:
                time.sleep(0.5)

        assert bridge_alive, "BlenderAgent Bridge failed to become healthy within 15 seconds."

        # 3. Instantiate MCP Client and Server
        bridge_client = BlenderBridgeClient(
            host="127.0.0.1",
            port=port,
            token=token,
            workspace_dir=temp_workspace,
        )
        mcp_server = create_mcp_server(name="test-e2e-mcp", client=bridge_client)

        async def run_mcp_flow():
            import json

            # Step 4: get_scene_info
            res_scene = await mcp_server.call_tool("get_scene_info", {})
            data_scene = json.loads(res_scene.content[0].text)
            assert data_scene["status"] == "success"
            assert data_scene["data"]["scene_name"] == "Scene"
            assert "counts" in data_scene["data"]

            # Step 5: create_primitive (Cube named AgentCube)
            res_create = await mcp_server.call_tool(
                "create_primitive",
                {"type": "cube", "name": "AgentCube", "location": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
            )
            data_create = json.loads(res_create.content[0].text)
            assert data_create["status"] == "success"
            assert data_create["data"]["name"] == "AgentCube"

            # Step 6: transform_object to (2, 0, 1)
            res_trans = await mcp_server.call_tool(
                "transform_object",
                {"name": "AgentCube", "location": [2.0, 0.0, 1.0]},
            )
            data_trans = json.loads(res_trans.content[0].text)
            assert data_trans["status"] == "success"
            assert data_trans["data"]["location"] == [2.0, 0.0, 1.0]

            # Step 7: set_material (Metallic blue)
            res_mat = await mcp_server.call_tool(
                "set_material",
                {
                    "name": "AgentCube",
                    "color": [0.0, 0.2, 0.9, 1.0],
                    "metallic": 0.9,
                    "roughness": 0.2,
                    "material_name": "AgentMetallicBlue",
                },
            )
            data_mat = json.loads(res_mat.content[0].text)
            assert data_mat["status"] == "success"
            assert data_mat["data"]["material_name"] == "AgentMetallicBlue"
            assert data_mat["data"]["metallic"] == 0.9
            assert data_mat["data"]["roughness"] == 0.2

            # Step 8: set_camera and lighting
            res_cam = await mcp_server.call_tool(
                "set_camera",
                {
                    "camera_name": "Camera",
                    "location": [6.0, -6.0, 5.0],
                    "rotation": [60.0, 0.0, 45.0],
                    "focal_length": 50.0,
                    "make_active": True,
                },
            )
            data_cam = json.loads(res_cam.content[0].text)
            assert data_cam["status"] == "success"
            assert data_cam["data"]["is_active_scene_camera"] is True

            # Step 9: render_preview
            render_filename = "renders/agent_demo_preview.png"
            res_render = await mcp_server.call_tool(
                "render_preview",
                {
                    "width": 320,
                    "height": 240,
                    "samples": 8,
                    "output_filename": render_filename,
                },
            )
            data_render = json.loads(res_render.content[0].text)
            assert data_render["status"] == "success"
            render_file = temp_workspace / render_filename
            assert render_file.exists(), "Render preview file was not found on disk."
            assert render_file.stat().st_size > 500, "Render preview file is unexpectedly empty."

            # Step 10: save_project as 'blenderagent_demo.blend'
            blend_filename = "blenderagent_demo.blend"
            res_save = await mcp_server.call_tool(
                "save_project",
                {"filename": blend_filename, "overwrite": True},
            )
            data_save = json.loads(res_save.content[0].text)
            assert data_save["status"] == "success"
            blend_file = temp_workspace / blend_filename
            assert blend_file.exists(), "Saved .blend file was not found on disk."
            assert blend_file.stat().st_size > 10000, ".blend file size is suspiciously small."

            # Step 11: get_object_info and verify properties
            res_obj = await mcp_server.call_tool("get_object_info", {"name": "AgentCube"})
            data_obj = json.loads(res_obj.content[0].text)
            assert data_obj["status"] == "success"
            assert data_obj["data"]["name"] == "AgentCube"
            assert data_obj["data"]["location"] == [2.0, 0.0, 1.0]
            assert "AgentMetallicBlue" in data_obj["data"]["materials"]

            # Step 12: Verify Blender remains responsive
            res_verify = await mcp_server.call_tool("get_scene_info", {})
            data_verify = json.loads(res_verify.content[0].text)
            assert data_verify["status"] == "success"
            obj_names = [o["name"] for o in data_verify["data"]["objects"]]
            assert "AgentCube" in obj_names

        asyncio.run(run_mcp_flow())

    finally:
        # Terminate Blender process
        try:
            proc.terminate()
            proc.wait(timeout=5.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
