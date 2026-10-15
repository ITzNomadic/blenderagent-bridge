# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('E:/Decalga/Proyecto blender/blenderagent-bridge/dist/blenderagent-mcp.exe', 'dist'), ('E:/Decalga/Proyecto blender/blenderagent-bridge/dist/blenderagent_bridge.zip', 'dist'), ('E:/Decalga/Proyecto blender/blenderagent-bridge/blender_manifest.toml', '.'), ('E:/Decalga/Proyecto blender/blenderagent-bridge/LICENSE', '.')]
binaries = []
hiddenimports = ['tomli', 'tomli_w', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog', 'httpx', 'ctypes', 'winreg', 'installer', 'installer.constants', 'installer.detector', 'installer.orchestrator', 'installer.gui', 'installer.addon_manager', 'installer.security_manager', 'installer.adapters', 'installer.adapters.base', 'installer.adapters.antigravity', 'installer.adapters.codex']
tmp_ret = collect_all('installer')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['installer/cli.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BlenderAgentBridge-Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
