"""Installer-owned history; opening the desktop never creates install events."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class InstallationHistory:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "history.sqlite3"

    def record(self, version, commit, changes):
        self.root.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS installations (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, previous_version TEXT, version TEXT NOT NULL, commit_sha TEXT NOT NULL, changes TEXT NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT version FROM installations ORDER BY id DESC LIMIT 1").fetchone()
            # Import only the last verified legacy update; do not invent older dates.
            if previous is None:
                legacy = self._legacy_result()
                if legacy:
                    db.execute("INSERT INTO installations(timestamp,previous_version,version,commit_sha,changes) VALUES (?,?,?,?,?)",
                               (legacy["time"], None, legacy["version"], "", "Release notes were not recorded for this installation."))
                    previous = (legacy["version"],)
            db.execute("INSERT INTO installations(timestamp,previous_version,version,commit_sha,changes) VALUES (?,?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), previous[0] if previous else None, version, commit, changes))
            db.commit()

    def _legacy_result(self):
        try:
            result = json.loads((self.root / "result.json").read_text(encoding="utf-8-sig"))
            if (result.get("status") == "installed" and isinstance(result.get("version"), str)
                    and isinstance(result.get("time"), str)):
                datetime.fromisoformat(result["time"])
                return result
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def recent(self, limit=50):
        if not self.path.exists():
            legacy = self._legacy_result()
            return ([dict(timestamp=legacy["time"], previous_version=None, version=legacy["version"],
                          commit_sha="", changes="Release notes were not recorded for this installation.")]
                    if legacy else [])
        with closing(sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)) as db:
            rows = db.execute("SELECT timestamp,previous_version,version,commit_sha,changes FROM installations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(("timestamp", "previous_version", "version", "commit_sha", "changes"), row)) for row in rows]
