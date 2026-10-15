# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['installer/cli.py'],
    pathex=['.'],
    binaries=[],
    datas=[('E:/Decalga/Proyecto blender/blenderagent-bridge/dist/blenderagent-mcp.exe', 'dist'), ('E:/Decalga/Proyecto blender/blenderagent-bridge/dist/blenderagent_bridge.zip', 'dist'), ('E:/Decalga/Proyecto blender/blenderagent-bridge/blender_manifest.toml', '.'), ('E:/Decalga/Proyecto blender/blenderagent-bridge/LICENSE', '.')],
    hiddenimports=['tomli', 'tomli_w', 'tkinter', 'tkinter.ttk', 'httpx', 'ctypes', 'winreg'],
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
