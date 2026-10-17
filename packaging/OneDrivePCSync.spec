# Build from the repository root with PyInstaller.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
datas = collect_data_files("qtawesome") + [
    (str(root / "CHANGELOG.md"), "."),
    (str(root / "ui" / "resources"), "ui/resources"),
    (str(root / "packaging" / "default-config.json"), "packaging"),
    (str(root / "src" / "build-info.json"), "src"),
    (str(root / "packaging" / "Apply-Update.ps1"), "packaging"),
]
a = Analysis([str(root / "desktop_entry.py")], pathex=[str(root)],
             binaries=[], datas=datas,
             hiddenimports=["win32gui", "win32api", "win32con"],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["graphify", "pytest", "tkinter", "matplotlib", "scipy"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OneDrivePCSync",
          icon=str(root / "ui" / "resources" / "app.ico"),
          version=str(root / "packaging" / "build-version-info.txt"),
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="OneDrivePCSync")
