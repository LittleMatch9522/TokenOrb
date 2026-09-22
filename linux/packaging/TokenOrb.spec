from pathlib import Path

project_root = Path(SPECPATH).resolve().parents[1]
linux_root = project_root / "linux"

analysis = Analysis(
    [str(linux_root / "tokenorb_app.py")],
    pathex=[str(linux_root)],
    binaries=[],
    datas=[(str(linux_root / "assets"), "assets")],
    hiddenimports=["PyQt5.sip"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TokenOrb",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
collated = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="TokenOrb",
)
