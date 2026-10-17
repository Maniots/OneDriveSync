"""Shared GUI/CLI run history, stored beside the chosen configuration."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing


class SyncHistory:
    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, mode, outcomes, dry_run=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, mode TEXT NOT NULL, dry_run INTEGER NOT NULL, outcomes TEXT NOT NULL)")
            values = [{"folder_id": o.folder_id, "folder_name": o.folder_name,
                       "direction": o.direction.value, "succeeded": o.succeeded,
                       "message": o.message,
                       "threshold_bypassed": o.threshold_bypassed} for o in outcomes]
            db.execute("INSERT INTO runs(timestamp, mode, dry_run, outcomes) VALUES (?, ?, ?, ?)",
                       (datetime.now(timezone.utc).isoformat(), mode, int(dry_run), json.dumps(values)))
            db.execute("DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 1000)")
            db.commit()

    def recent(self, limit=100):
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)) as db:
            # An empty/new database can be observed while the first writer starts.
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='runs'").fetchone():
                return []
            rows = db.execute("SELECT id,timestamp,mode,dry_run,outcomes FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "timestamp": r[1], "mode": r[2], "dry_run": bool(r[3]),
                 "outcomes": json.loads(r[4])} for r in rows]

    def latest_folders(self):
        latest = {}
        for run in self.recent(1000):
            for outcome in run["outcomes"]:
                latest.setdefault(outcome["folder_id"], dict(outcome, timestamp=run["timestamp"], dry_run=run["dry_run"]))
        return latest
