"""Single source for build identity used by the desktop and release pipeline."""
import json
from pathlib import Path

BASE_VERSION = "1.1.0"
REPOSITORY = "Maniots/OneDriveSync"


def build_info() -> dict:
    path = Path(__file__).with_name("build-info.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": BASE_VERSION + ".0", "commit": "", "repository": REPOSITORY}


VERSION = build_info()["version"]
