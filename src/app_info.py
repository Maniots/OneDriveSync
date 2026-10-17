"""Single source for build identity used by the desktop and release pipeline."""
import json
from pathlib import Path

APP_NAME = "EverySync"
BASE_VERSION = "1.4.0"
REPOSITORY = "Maniots/OneDriveSync"


def build_info() -> dict:
    path = Path(__file__).with_name("build-info.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": BASE_VERSION + ".0", "commit": "", "repository": REPOSITORY}


VERSION = build_info()["version"]


def release_notes():
    path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    marker = f"## {BASE_VERSION} "
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    return (marker + section).strip()
