"""Automated reproducible build pipeline for BlenderAgent Bridge v0.2.0 Windows Installer."""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys

repo_root = pathlib.Path(__file__).parent.parent.resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from installer.addon_manager import BlenderAddonManager
from installer.constants import ADDON_ID, MCP_LAUNCHER_EXE_NAME, VERSION


def compute_sha256(filepath: pathlib.Path) -> str:
    """Calculate the cryptographic SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_all():
    repo_root = pathlib.Path(__file__).parent.parent.resolve()
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"  BUILDING BLENDERAGENT BRIDGE v{VERSION} — ONE-CLICK INSTALLER")
    print("=" * 70)

    # 1. Build extension zip
    print("\n[*] Step 1: Packaging Blender extension zip...")
    addon_mgr = BlenderAddonManager()
    zip_path = dist_dir / f"{ADDON_ID}.zip"
    addon_mgr.build_extension_zip(zip_path)
    print(f"[+] Extension zip created: {zip_path} ({zip_path.stat().st_size:,} bytes)")

    # 2. Compile standalone MCP Launcher (blenderagent-mcp.exe) if not built
    launcher_exe = dist_dir / MCP_LAUNCHER_EXE_NAME
    pyinstaller_exe = sys.executable.replace("python.exe", "pyinstaller.exe")
    if not pathlib.Path(pyinstaller_exe).exists():
        pyinstaller_exe = "pyinstaller"

    print(f"\n[*] Step 2: Compiling {MCP_LAUNCHER_EXE_NAME} via PyInstaller...")
    cmd_mcp = [
        pyinstaller_exe,
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "blenderagent-mcp",
        "--distpath",
        str(dist_dir),
        "--paths",
        ".",
        "mcp_server/launcher.py",
    ]
    res = subprocess.run(cmd_mcp, cwd=str(repo_root))
    if res.returncode != 0:
        print(f"[!] Error building {MCP_LAUNCHER_EXE_NAME}")
        sys.exit(1)
    print(f"[+] {MCP_LAUNCHER_EXE_NAME} compiled successfully.")

    # 3. Compile Single-File Windows Installer (BlenderAgentBridge-Setup.exe)
    print("\n[*] Step 3: Compiling BlenderAgentBridge-Setup.exe...")
    setup_name = "BlenderAgentBridge-Setup"

    # Define bundled assets using Windows ';' separator
    add_data_args = [
        f"--add-data={dist_dir / MCP_LAUNCHER_EXE_NAME};dist",
        f"--add-data={zip_path};dist",
        f"--add-data={repo_root / 'blender_manifest.toml'};.",
        f"--add-data={repo_root / 'LICENSE'};.",
    ]

    hidden_imports = [
        "--collect-all=installer",
        "--hidden-import=tomli",
        "--hidden-import=tomli_w",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=tkinter.messagebox",
        "--hidden-import=tkinter.filedialog",
        "--hidden-import=httpx",
        "--hidden-import=ctypes",
        "--hidden-import=winreg",
        "--hidden-import=installer",
        "--hidden-import=installer.constants",
        "--hidden-import=installer.detector",
        "--hidden-import=installer.orchestrator",
        "--hidden-import=installer.gui",
        "--hidden-import=installer.addon_manager",
        "--hidden-import=installer.security_manager",
        "--hidden-import=installer.adapters",
        "--hidden-import=installer.adapters.base",
        "--hidden-import=installer.adapters.antigravity",
        "--hidden-import=installer.adapters.codex",
    ]

    cmd_setup = [
        pyinstaller_exe,
        "--noconfirm",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name",
        setup_name,
        "--distpath",
        str(dist_dir),
        "--paths",
        ".",
        *add_data_args,
        *hidden_imports,
        "installer/cli.py",
    ]

    res_setup = subprocess.run(cmd_setup, cwd=str(repo_root))
    if res_setup.returncode != 0:
        print("[!] Error compiling BlenderAgentBridge-Setup.exe")
        sys.exit(1)

    setup_exe = dist_dir / f"{setup_name}.exe"
    print(f"[+] Setup Installer created: {setup_exe} ({setup_exe.stat().st_size:,} bytes)")

    # 4. Generate SHA-256 Checksums
    print("\n[*] Step 4: Computing SHA-256 Checksums...")
    artifacts = [
        setup_exe,
        launcher_exe,
        zip_path,
    ]

    sums_path = dist_dir / "SHA256SUMS.txt"
    with open(sums_path, "w", encoding="utf-8") as f:
        for art in artifacts:
            if art.exists():
                digest = compute_sha256(art)
                f.write(f"{digest}  {art.name}\n")
                print(f"    {digest}  {art.name}")

    print(f"[+] Checksums saved to: {sums_path}")
    print("\n" + "=" * 70)
    print("  BUILD SUCCESSFUL — ALL DELIVERABLES READY")
    print("=" * 70)


if __name__ == "__main__":
    build_all()
