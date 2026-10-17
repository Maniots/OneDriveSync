"""Create build identity before packaging and a manifest after compilation."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.app_info import APP_NAME, BASE_VERSION, REPOSITORY, release_notes


def windows_version_info(version):
    """PyInstaller's version resource, keeping the executable upgrade identity."""
    numbers = tuple(int(component) for component in version.split("."))
    if len(numbers) != 4 or any(not 0 <= component <= 65535 for component in numbers):
        raise ValueError("Windows versions require four components between 0 and 65535")
    fields = {"CompanyName": APP_NAME, "FileDescription": APP_NAME,
              "FileVersion": version, "InternalName": "OneDrivePCSync",
              "OriginalFilename": "OneDrivePCSync.exe", "ProductName": APP_NAME,
              "ProductVersion": version}
    strings = ",\n".join(f"        StringStruct({key!r}, {value!r})" for key, value in fields.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r},
                   mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
{strings}
      ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "manifest"])
    parser.add_argument("--build-number", type=int, default=0)
    args = parser.parse_args()
    if args.action == "build":
        notes = release_notes()
        if len(notes.encode("utf-8")) > 4096:
            raise ValueError("Release notes must fit within 4096 UTF-8 bytes")
        if not 0 <= args.build_number <= 65535:
            parser.error("Build number must be between 0 and 65535")
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        info = {"version": f"{BASE_VERSION}.{args.build_number}",
                "commit": commit, "repository": REPOSITORY, "changes": notes}
        (ROOT / "packaging/build-version-info.txt").write_text(
            windows_version_info(info["version"]), encoding="utf-8")
        (ROOT / "src/build-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        (ROOT / "packaging/build-version.iss").write_text(
            f'#define AppVersion "{info["version"]}"\n', encoding="utf-8")
        print(info["version"])
    else:
        info = json.loads((ROOT / "src/build-info.json").read_text(encoding="utf-8"))
        installer = ROOT / "dist/installer" / f'OneDrivePCSync-Setup-{info["version"]}.exe'
        canonical = installer.with_name(f'EverySync-Setup-{info["version"]}.exe')
        # Installed 1.3 clients strictly require this legacy asset name.
        shutil.copyfile(canonical, installer)
        with installer.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        manifest = {**info, "schema": 1, "channel": "master",
                    "installer": installer.name, "sha256": digest,
                    "size": installer.stat().st_size}
        (installer.parent / "update.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        (installer.parent / "release-notes.md").write_text(info["changes"], encoding="utf-8")
        print(installer)


if __name__ == "__main__":
    main()
