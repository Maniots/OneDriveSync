# OneDrive PC Sync

A safety-first Windows application that synchronizes explicitly chosen
application data folders between the local PC and OneDrive - on **startup**
(download from OneDrive) and **shutdown** (upload to OneDrive).

It exists to solve one problem: keeping small, important per-application
data folders (game saves, editor settings, app configs) in sync across
machines via OneDrive, **without** the risk of a full `AppData` mirror
wiping out live application state.

## Why not just sync all of AppData?

`AppData` contains active databases, caches, locked files, and installed
application binaries. Mirroring it (e.g. `robocopy /MIR`) is destructive
and unsafe. This project **only** syncs folders you explicitly list in
`config.json`, and **never** deletes anything - it is strictly additive
(create missing folders, copy missing files, update changed files).

## Project structure

```
OneDrivePCSync/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── config.json          # User-editable list of folders to sync
│
├── main.py               # Entry point (--mode startup|shutdown)
│
├── src/
│   ├── __init__.py
│   ├── config.py          # Typed configuration dataclasses/enums
│   ├── config_manager.py  # Loads/validates config.json
│   ├── sync_manager.py    # All safety decisions + orchestration
│   ├── robocopy_manager.py# Safe, non-destructive robocopy wrapper
│   ├── logger.py          # Centralized logging setup
│   ├── exceptions.py      # Application exception hierarchy
│   └── utils.py           # Env var expansion, dangerous-path checks, ratios
│
├── logs/                  # Rotating log files (created at runtime)
├── backups/               # Reserved for future pre-sync backups
├── data/                  # Reserved for local application state/cache
│
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_sync.py
    └── test_robocopy.py
```

## Installation

Requires Python 3.12+ on Windows. No third-party dependencies.

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run at logon (typically downloads OneDrive -> local)
python main.py --mode startup

# Run at logoff/shutdown (typically uploads local -> OneDrive)
python main.py --mode shutdown

# Preview without copying or creating anything
python main.py --mode startup --dry-run
```

Wire these into Windows Task Scheduler with triggers "At log on" and
"On workstation lock" / "On logoff" respectively.

## Configuring folders

Edit `config.json` and add an entry under `"folders"` for each folder you
want synchronized. **Only list explicit application subfolders** - never
`AppData`, `AppData\Local`, or `AppData\Roaming` themselves; the app will
refuse to load a config that tries to sync one of these.

```json
{
    "id": "elden_ring",
    "name": "Elden Ring Save",
    "enabled": true,
    "local_path": "%APPDATA%\\EldenRing",
    "onedrive_path": "%OneDrive%\\PCSync\\AppData\\Roaming\\EldenRing",
    "minimum_sync_percentage": 80,
    "verify_after_sync": true,
    "create_destination": true
}
```

`minimum_sync_percentage` is the safety threshold: if the smaller of the
two file counts (source vs. destination) is below this percentage of the
larger, the sync for that folder aborts rather than risk overwriting
recent data with stale data (or vice versa).

## Safety guarantees

- **No destructive robocopy flags, ever.** `/MIR`, `/PURGE`, `/MOV`,
  `/MOVE` are hard-blocked in `robocopy_manager.py`, independent of config.
- **Dangerous root rejection**, checked both when `config.json` loads and
  again immediately before every sync.
- **File-count ratio abort**, per the `minimum_sync_percentage` rule above.
- **Per-folder isolation** - one folder failing never stops the others.
- **Dry-run mode** via `general.dry_run` in `config.json` or `--dry-run`.
- **Post-sync verification** (optional) checks the destination file count
  never dropped below the source's.

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

All tests run against real temporary directories with `dry_run=True`, so
no files are ever copied or deleted during testing.