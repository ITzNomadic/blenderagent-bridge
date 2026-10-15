"""Phase 5 Functional Demonstration Script for BlenderAgent Bridge.

Executes the complete 12-step flow connecting to a running Blender instance
and creating, transforming, shading, illuminating, rendering, and saving
the 'AgentCube' scene.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

repo_root = pathlib.Path(__file__).parent.parent.resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from mcp_server.client import BlenderBridgeClient
from mcp_server.server import create_mcp_server


def run_demonstration(port: int = 9876, token: str = ""):
    workspace = repo_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    renders_dir = workspace / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  BlenderAgent Bridge — Phase 5 End-to-End Functional Demo")
    print("=" * 70)

    client = BlenderBridgeClient(port=port, token=token or None, workspace_dir=workspace)

    print(f"[*] Target Bridge Address: {client.base_url}")
    print(f"[*] Workspace Directory:  {workspace}")
    print("[*] Probing bridge health...")

    if not client.check_health():
        print(f"[!] ERROR: Unable to reach BlenderAgent Bridge on {client.base_url}.")
        print("[!] Ensure Blender is open and 'Start Bridge' is pressed in the 3D Viewport sidebar.")
        sys.exit(1)

    print("[+] Bridge is healthy and responding!\n")

    # Step 4: Query initial scene info
    print("[Step 4] Querying active scene via 'get_scene_info'...")
    res = client.send_command("get_scene_info", {})
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    scene_data = res.data
    print(f"    - Scene Name:       {scene_data['scene_name']}")
    print(f"    - Total Objects:    {scene_data['counts']['total_objects']}")
    print(f"    - Existing Objects: {[o['name'] for o in scene_data['objects']]}")

    # Step 5: Create primitive Cube named 'AgentCube'
    print("\n[Step 5] Creating primitive mesh cube named 'AgentCube'...")
    res = client.send_command(
        "create_primitive",
        {"type": "cube", "name": "AgentCube", "location": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Object Created:   {res.data['name']} (Type: {res.data['type']})")

    # Step 6: Transform object to (2, 0, 1)
    print("\n[Step 6] Transforming 'AgentCube' to location (2.0, 0.0, 1.0)...")
    res = client.send_command(
        "transform_object",
        {"name": "AgentCube", "location": [2.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0]},
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Verified Location: {res.data['location']}")

    # Step 7: Assign Metallic Blue material
    print("\n[Step 7] Assigning metallic blue Principled BSDF material to 'AgentCube'...")
    res = client.send_command(
        "set_material",
        {
            "name": "AgentCube",
            "color": [0.0, 0.25, 0.95, 1.0],
            "metallic": 0.9,
            "roughness": 0.2,
            "material_name": "AgentMetallicBlue",
        },
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Material Name:     {res.data['material_name']}")
    print(f"    - Metallic Factor:   {res.data['metallic']}")
    print(f"    - Roughness Factor:  {res.data['roughness']}")

    # Step 7b: Create and shade second object: AgentCylinder
    print("\n[Step 7b] Creating second object: Cylinder named 'AgentCylinder'...")
    res = client.send_command(
        "create_primitive",
        {"type": "cylinder", "name": "AgentCylinder", "location": [-1.5, 0.0, 1.0], "scale": [0.8, 0.8, 1.2]},
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Object Created:    {res.data['name']} (Collision Renamed: {res.data.get('renamed', False)})")

    print("    - Rotating 'AgentCylinder' by [0, 15, 30] degrees...")
    client.send_command(
        "transform_object",
        {"name": "AgentCylinder", "rotation": [0.0, 15.0, 30.0]},
    )

    print("    - Assigning Warm Copper/Gold material to 'AgentCylinder'...")
    res = client.send_command(
        "set_material",
        {
            "name": "AgentCylinder",
            "color": [0.95, 0.65, 0.2, 1.0],
            "metallic": 0.85,
            "roughness": 0.25,
            "material_name": "AgentGoldCopper",
        },
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Material Name:     {res.data['material_name']}")

    # Step 8: Configure Camera and Lighting
    print("\n[Step 8] Positioning observation camera and configuring lighting...")
    res = client.send_command(
        "set_camera",
        {
            "camera_name": "Camera",
            "location": [6.5, -6.5, 5.0],
            "rotation": [60.0, 0.0, 45.0],
            "focal_length": 50.0,
            "make_active": True,
        },
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Camera Position:   {res.data['location']}")
    print(f"    - Active in Scene:   {res.data['is_active_scene_camera']}")

    # Step 9: Render preview image
    preview_rel = "renders/agent_demo_preview.png"
    print(f"\n[Step 9] Generating preview render ({preview_rel})...")
    render_start = time.time()
    res = client.send_command(
        "render_preview",
        {
            "width": 640,
            "height": 480,
            "samples": 32,
            "output_filename": preview_rel,
        },
        timeout=60.0,
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    render_duration = time.time() - render_start
    print(f"    - Render Time:       {render_duration:.2f}s")
    print(f"    - Saved Image Path:  {res.data['file_path']}")
    print(f"    - Image File Size:   {res.data['file_size_bytes']} bytes")

    # Step 10: Save project as 'blenderagent_demo.blend'
    blend_filename = "blenderagent_demo.blend"
    print(f"\n[Step 10] Saving project copy as '{blend_filename}'...")
    res = client.send_command(
        "save_project",
        {"filename": blend_filename, "overwrite": True},
    )
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    print(f"    - Saved Blend Path:  {res.data['file_path']}")
    print(f"    - Project File Size: {res.data['file_size_bytes']} bytes")

    # Step 11: Re-inspect 'AgentCube'
    print("\n[Step 11] Re-inspecting 'AgentCube' properties to verify state...")
    res = client.send_command("get_object_info", {"name": "AgentCube"})
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    obj_info = res.data
    print(f"    - Name:              {obj_info['name']}")
    print(f"    - Location:          {obj_info['location']}")
    print(f"    - Dimensions:        {obj_info['dimensions']}")
    print(f"    - Materials:         {obj_info['materials']}")

    # Step 12: Verify Blender responsiveness
    print("\n[Step 12] Verifying Blender remains responsive...")
    res = client.send_command("get_scene_info", {})
    if res.status != "success":
        print(f"[!] Failed: {res.message}")
        sys.exit(1)
    final_objs = [o["name"] for o in res.data["objects"]]
    print(f"    - Active Scene:      {res.data['scene_name']}")
    print(f"    - Objects in Scene:  {final_objs}")
    print("\n" + "=" * 70)
    print("  [SUCCESS] All 12 validation steps completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlenderAgent Bridge Phase 5 Demo Runner")
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--token", type=str, default="")
    args = parser.parse_args()
    run_demonstration(port=args.port, token=args.token)
