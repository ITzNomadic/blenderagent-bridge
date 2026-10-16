"""Script to package all deliverables and complete source code into the Windows distribution zip."""

import hashlib
import os
import pathlib
import shutil
import zipfile

from installer.constants import VERSION

repo_root = pathlib.Path(r"e:\Decalga\Proyecto blender\blenderagent-bridge").resolve()
dist_dir = repo_root / "dist"
target_dir = pathlib.Path(r"e:\Decalga").resolve()

setup_exe = dist_dir / "BlenderAgentBridge-Setup.exe"
mcp_exe = dist_dir / "blenderagent-mcp.exe"
addon_zip = dist_dir / "blenderagent_bridge.zip"
sums_file = dist_dir / "SHA256SUMS.txt"

print("[*] 1. Copying standalone Setup.exe to e:\\Decalga\\...")
dst_setup = target_dir / "BlenderAgentBridge-Setup.exe"
shutil.copy2(setup_exe, dst_setup)
print(f"[+] Updated: {dst_setup} ({dst_setup.stat().st_size:,} bytes)")

print(f"\n[*] 2. Assembling BlenderAgentBridge-v{VERSION}-Windows.zip...")
target_zip = target_dir / f"BlenderAgentBridge-v{VERSION}-Windows.zip"

def compute_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    # 1. Primary Binaries & Canonical Addon at Root
    zf.write(setup_exe, arcname="BlenderAgentBridge-Setup.exe")
    zf.write(mcp_exe, arcname="blenderagent-mcp.exe")
    zf.write(addon_zip, arcname="blenderagent_bridge.zip")
    zf.write(sums_file, arcname="SHA256SUMS.txt")

    # 2. Complete Source Code Tree for full GPT / Auditor visibility
    source_dirs = ["addon", "installer", "mcp_server", "tests"]
    for sdir in source_dirs:
        dirpath = repo_root / sdir
        for root, dirs, files in os.walk(dirpath):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.endswith(".egg-info")]
            for file in files:
                if file.endswith((".pyc", ".pyo")):
                    continue
                fp = pathlib.Path(root) / file
                rel = fp.relative_to(repo_root)
                zf.write(fp, arcname=f"source/{rel.as_posix()}")

    # 3. Root project config and docs
    for rfile in ["pyproject.toml", "blender_manifest.toml", "README.md", "LICENSE"]:
        fp = repo_root / rfile
        if fp.exists():
            zf.write(fp, arcname=f"source/{rfile}")

print(f"[+] Zip assembled: {target_zip} ({target_zip.stat().st_size:,} bytes)")

# Compute final checksum of zip
zip_hash = compute_sha256(target_zip)
print(f"[+] SHA256 of BlenderAgentBridge-v0.2.0-Windows.zip: {zip_hash}")

print("\n[*] Verifying Zip Contents:")
with zipfile.ZipFile(target_zip, "r") as zf:
    names = zf.namelist()
    print(f"Total entries: {len(names)}")
    root_entries = [n for n in names if "/" not in n]
    print(f"Root files: {root_entries}")
    source_count = len([n for n in names if n.startswith("source/")])
    print(f"Source files included: {source_count}")

print("\n[SUCCESS] All distribution deliverables updated cleanly!")
