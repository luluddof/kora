# -*- mode: python ; coding: utf-8 -*-


# Tous les modules du jeu : certains ne sont appeles que par le tableau des
# systemes (systems.py, import a la demande) et PyInstaller ne les verrait
# pas (tests/test_architecture.py le verifie).
import glob
import os

KORA_MODULES = sorted(
    "src.kora." + os.path.splitext(os.path.basename(p))[0]
    for p in glob.glob(os.path.join(SPECPATH, "src", "kora", "*.py"))
    if not p.endswith("__init__.py")
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('data/kora_map.json', 'data'), ('data/fonts', 'data/fonts'), ('data/icons', 'data/icons'), ('data/music', 'data/music')],
    hiddenimports=KORA_MODULES,
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
    [],
    exclude_binaries=True,
    name='Kora',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Kora',
)
