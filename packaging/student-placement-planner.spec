# PyInstaller specification for the self-contained desktop application.

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).resolve().parent

offline_datas = []
offline_binaries = []
offline_hidden = []
platform_binaries = []
valhalla_spec = importlib.util.find_spec("valhalla")
if valhalla_spec is not None and valhalla_spec.origin is not None:
    valhalla_dir = Path(valhalla_spec.origin).parent
    suffix = ".exe" if sys.platform == "win32" else ""
    for builder in ("valhalla_build_admins", "valhalla_build_tiles"):
        offline_binaries.append((str(valhalla_dir / "bin" / f"{builder}{suffix}"), "valhalla/bin"))
    offline_hidden.extend(
        [
            "valhalla",
            "valhalla._valhalla",
            "valhalla.actor",
            "valhalla.config",
            "valhalla.valhalla_build_config",
        ]
    )
if importlib.util.find_spec("osmium") is not None:
    package_datas, package_binaries, package_hidden = collect_all("osmium")
    offline_datas.extend(package_datas)
    offline_binaries.extend(package_binaries)
    offline_hidden.extend(package_hidden)

if sys.platform == "win32":
    # OR-Tools' native CP-SAT module links against the VC143 C++ runtime. PyInstaller
    # intentionally treats that runtime as a system library, but clean Windows PCs do
    # not necessarily have it. Use Microsoft's supported app-local deployment files.
    runtime_names = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
    runtime_candidates = []
    redist_root = os.environ.get("VCToolsRedistDir")
    if redist_root:
        runtime_candidates.append(Path(redist_root) / "x64" / "Microsoft.VC143.CRT")
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    visual_studio = program_files / "Microsoft Visual Studio" / "2022"
    runtime_candidates.extend(
        visual_studio.glob("*/VC/Redist/MSVC/*/x64/Microsoft.VC143.CRT")
    )
    # Hosted runners install the official x64 Redistributable even when the
    # Visual Studio app-local folder is absent. Its System32 copies are the same
    # redistributable runtime and are copied into our private application folder.
    system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
    runtime_candidates.append(system_root / "System32")
    runtime_dir = next(
        (
            candidate
            for candidate in sorted(runtime_candidates, key=str, reverse=True)
            if all((candidate / name).is_file() for name in runtime_names)
        ),
        None,
    )
    if runtime_dir is None:
        raise RuntimeError("Microsoft VC143 x64 app-local runtime files were not found")
    platform_binaries.extend((str(runtime_dir / name), ".") for name in runtime_names)

datas = [
    (str(ROOT / "src/placement_optimizer/assets"), "placement_optimizer/assets"),
    (str(ROOT / "LICENSE"), "."),
    *offline_datas,
    *copy_metadata("student-placement-planner"),
    *copy_metadata("pydantic"),
]

icon = ROOT / "assets/app-icon.ico"
if sys.platform == "darwin":
    icon = Path(os.environ.get("SPP_MACOS_ICON", ROOT / "packaging/app-icon.icns"))

analysis = Analysis(
    [str(ROOT / "src/placement_optimizer/__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[*offline_binaries, *platform_binaries],
    datas=datas,
    hiddenimports=offline_hidden,
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
