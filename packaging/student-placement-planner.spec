# PyInstaller specification for the self-contained desktop application.

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).resolve().parent

valhalla_hidden = []
if importlib.util.find_spec("valhalla") is not None:
    # Only the Actor path is needed at runtime. collect_all("valhalla") would also
    # bundle tile-building executables and development helpers, adding tens of MB.
    valhalla_hidden = [
        "valhalla",
        "valhalla._valhalla",
        "valhalla.actor",
        "valhalla.config",
        "valhalla.valhalla_build_config",
    ]

datas = [
    (str(ROOT / "src/placement_optimizer/assets"), "placement_optimizer/assets"),
    (str(ROOT / "LICENSE"), "."),
    *copy_metadata("student-placement-planner"),
    *copy_metadata("pydantic"),
]

icon = ROOT / "assets/app-icon.ico"
if sys.platform == "darwin":
    icon = Path(os.environ.get("SPP_MACOS_ICON", ROOT / "packaging/app-icon.icns"))

analysis = Analysis(
    [str(ROOT / "src/placement_optimizer/__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=valhalla_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Student Placement Planner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon),
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Student Placement Planner",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="Student Placement Planner.app",
        icon=str(icon),
        bundle_identifier="com.github.nklisch.student-placement-planner",
        info_plist={
            "CFBundleDisplayName": "Student Placement Planner",
            "CFBundleName": "Student Placement Planner",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "13.0",
            "LSApplicationCategoryType": "public.app-category.productivity",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Student Placement Planner project",
                    "CFBundleTypeRole": "Editor",
                    "CFBundleTypeExtensions": ["spp"],
                }
            ],
        },
    )
