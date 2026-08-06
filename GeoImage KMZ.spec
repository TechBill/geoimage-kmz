# -*- mode: python ; coding: utf-8 -*-
# Cross-platform spec file for GeoImage KMZ
# Works on both Windows and macOS
#
# Usage:
#   python -m PyInstaller --noconfirm --clean "GeoImage KMZ.spec"
#
# Platform detection:
# - Windows: Creates single-file EXE with icon.ico
# - macOS:   Creates .app bundle with icon.icns

import sys
from PyInstaller.utils.hooks import collect_all

# Detect platform
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

datas = []
binaries = []
hiddenimports = []

# Collect NumPy
tmp_ret = collect_all("numpy")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Collect Pillow (PIL)
tmp_ret = collect_all("PIL")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Platform-specific: bundle icon for Windows onefile
if IS_WINDOWS:
    datas += [("assets\\icon.ico", "assets")]

# Set icon path based on platform
if IS_WINDOWS:
    icon_path = "assets\\icon.ico"
elif IS_MAC:
    icon_path = "assets/icon.icns"
else:
    icon_path = None

a = Analysis(
    ["geoimage_kmz.py"],
    pathex=[],
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

if IS_WINDOWS:
    # Windows: Single-file EXE (onefile mode)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="GeoImage KMZ",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # No console window for tkinter GUI
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
    )

else:
    # macOS/Linux: Directory mode with COLLECT (and BUNDLE for macOS)
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="GeoImage KMZ",
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
        icon=[icon_path] if icon_path else None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="GeoImage KMZ",
    )

    if IS_MAC:
        # macOS: Create .app bundle
        app = BUNDLE(
            coll,
            name="GeoImage KMZ.app",
            icon=icon_path,
            bundle_identifier=None,
            info_plist={
                "CFBundleShortVersionString": "2.1",
                "CFBundleVersion": "2.1",
                "NSHighResolutionCapable": True,
            },
        )
