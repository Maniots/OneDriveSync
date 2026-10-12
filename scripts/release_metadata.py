"""Create build identity before packaging and a manifest after compilation."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.app_info import BASE_VERSION, REPOSITORY


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "manifest"])
    parser.add_argument("--build-number", type=int, default=0)
    args = parser.parse_args()
    if args.action == "build":
        if not 0 <= args.build_number <= 65535:
            parser.error("Build number must be between 0 and 65535")
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        info = {"version": f"{BASE_VERSION}.{args.build_number}",
                "commit": commit, "repository": REPOSITORY}
        (ROOT / "src/build-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        (ROOT / "packaging/build-version.iss").write_text(
            f'#define AppVersion "{info["version"]}"\n', encoding="utf-8")
        print(info["version"])
    else:
        info = json.loads((ROOT / "src/build-info.json").read_text())
        installer = ROOT / "dist/installer" / f'OneDrivePCSync-Setup-{info["version"]}.exe'
        with installer.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        manifest = {**info, "schema": 1, "channel": "master",
                    "installer": installer.name, "sha256": digest,
                    "size": installer.stat().st_size}
        (installer.parent / "update.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(installer)


if __name__ == "__main__":
    main()
