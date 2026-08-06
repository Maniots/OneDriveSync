# Graph Report - .  (2026-07-30)

## Corpus Check
- Corpus is ~17,958 words - fits in a single context window. You may not need a graph.

## Summary
- 323 nodes · 801 edges · 14 communities (13 shown, 1 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 43 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Config & Settings
- Backup Management
- Safety Philosophy & Sync Principles
- Logging & Main Entry
- Robocopy Operations
- Sync Manager & Folder Sync
- Single Instance & Locking
- Testing & Utilities
- Shutdown Monitor
- Scheduled Tasks (Sync)
- Scheduled Tasks (Monitor)
- Branch Metadata

## God Nodes (most connected - your core abstractions)
1. `ConfigManager` - 38 edges
2. `SyncManager` - 34 edges
3. `OneDrive PC Sync Project Memory` - 26 edges
4. `RobocopyManager` - 25 edges
5. `BackupManager` - 22 edges
6. `RobocopySettings` - 21 edges
7. `FolderSyncOutcome` - 21 edges
8. `BackupSettings` - 20 edges
9. `FolderSyncConfig` - 19 edges
10. `SyncDirection` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Non-Destructive Sync` --semantically_similar_to--> `Dangerous Root Path Rejection`  [INFERRED] [semantically similar]
  README.md → PROJECT_MEMORY.md
- `Non-Destructive Sync` --semantically_similar_to--> `Non-Destructive robocopy Flag Enforcement`  [INFERRED] [semantically similar]
  README.md → PROJECT_MEMORY.md
- `main()` --calls--> `acquire_single_instance_lock()`  [EXTRACTED]
  main.py → src/single_instance.py
- `_make_app_config_with_backup()` --calls--> `GeneralSettings`  [EXTRACTED]
  tests/test_backup.py → src/config.py
- `_make_config()` --calls--> `GeneralSettings`  [EXTRACTED]
  tests/test_sync.py → src/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Safety Architecture Flow** — dangerous_root_rejection, safety_threshold, non_destructive_robocopy, pre_upload_backup, post_sync_verification, single_instance_lock [EXTRACTED 1.00]
- **Sync Manager Orchestration** — src_sync_manager, src_robocopy_manager, src_backup_manager, src_utils, src_config_manager [EXTRACTED 1.00]
- **Shutdown Signal Handling** — src_shutdown_monitor, wm_queryendsession, wm_endsession, pywin32 [EXTRACTED 1.00]

## Communities (14 total, 1 thin omitted)

### Community 0 - "Config & Settings"
Cohesion: 0.09
Nodes (40): Any, Enum, GeneralSettings, LogLevel, ConfigManager, Path, config_manager.py Loads config.json from disk, expands environment variables in…, Parse and validate a folder's optional "backup" section. Returns None if the… (+32 more)

### Community 1 - "Backup Management"
Cohesion: 0.11
Nodes (40): date, BackupManager, Path, Compress every file under source_dir into a zip archive, preserving the…, Delete backup archives older than retention_days. Retention is calculated based…, Public method to prune expired backups. This can be called independently (e.g.,…, Creates and prunes daily rolling pre-upload backups for a single folder., Create (or replace) today's backup of the OneDrive folder. This method… (+32 more)

### Community 2 - "Safety Philosophy & Sync Principles"
Cohesion: 0.08
Nodes (39): Claude Code Project Instructions, config.json, Dangerous Root Path Rejection, Exception, Non-Destructive robocopy Flag Enforcement, Non-Destructive Sync, Periodic Upload (15-min Safety Net), Post-Sync Verification (+31 more)

### Community 3 - "Logging & Main Entry"
Cohesion: 0.09
Nodes (31): Logger, main(), parse_arguments(), Namespace, main.py Entry point for OneDrive PC Sync. Usage: python main.py --mode startup…, Parse command-line arguments. Args: argv: Argument list (typically…, Application entry point. Args: argv: Optional argument list override (used for…, get_logger() (+23 more)

### Community 4 - "Robocopy Operations"
Cohesion: 0.11
Nodes (27): Settings that control how robocopy is invoked. These settings NEVER include…, RobocopySettings, Path, Defense-in-depth: verify no destructive flag ever slipped in. This is a hard…, Execute robocopy for a single source/destination pair. Args: source: Source…, Builds and safely executes robocopy commands., Args: settings: Robocopy tuning parameters from configuration. dry_run: If…, Build a safe, non-destructive robocopy command. Args: source: Source directory.… (+19 more)

### Community 5 - "Sync Manager & Folder Sync"
Cohesion: 0.14
Nodes (16): AppConfig, FolderSyncConfig, Configuration for a single folder synchronization pair. local_path and…, Top-level application configuration, fully resolved and validated., Return only the folders that are enabled for synchronization., FolderSyncOutcome, Path, Determine source/destination based on sync direction. DOWNLOAD: OneDrive ->… (+8 more)

### Community 6 - "Single Instance & Locking"
Cohesion: 0.14
Nodes (18): IO, Single-Instance Lock, acquire_single_instance_lock(), Path, single_instance.py Ensures only one OneDrivePCSync sync runs at a time on this…, Attempt to become the only running OneDrivePCSync instance system-wide. Args:…, fake_windows(), _FakeMsvcrt (+10 more)

### Community 7 - "Testing & Utilities"
Cohesion: 0.18
Nodes (22): parametrize, Outcome of a single robocopy invocation., RobocopyResult, calculate_sync_percentage(), is_dangerous_root_path(), Determine whether a path is a forbidden "dangerous root" folder. A path is…, Calculate the safety ratio between two file counts, as a percentage. The ratio…, _make_config() (+14 more)

### Community 8 - "Shutdown Monitor"
Cohesion: 0.13
Nodes (14): pywin32 Dependency, Third-party Dependencies, main(), shutdown_monitor.py A resident program that runs at user logon and waits for…, Register the hidden window class., Create the hidden message-only window. Using HWND_MESSAGE (-3) as the parent…, Run the Windows message loop. GetMessage blocks efficiently until a message…, Clean up the hidden window and unregister its class. (+6 more)

### Community 9 - "Scheduled Tasks (Sync)"
Cohesion: 0.32
Nodes (4): New-OneDrivePCSyncTask(), Remove-ExistingTask(), Write-Info(), Write-Ok()

### Community 10 - "Scheduled Tasks (Monitor)"
Cohesion: 0.32
Nodes (4): New-OneDrivePCSyncMonitorTask(), Remove-ExistingTask(), Write-Info(), Write-Ok()

## Knowledge Gaps
- **4 isolated node(s):** `Claude Code Project Instructions`, `shutdown-management Branch`, `main.py`, `config.json`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConfigManager` connect `Config & Settings` to `Backup Management`, `Logging & Main Entry`, `Robocopy Operations`, `Sync Manager & Folder Sync`?**
  _High betweenness centrality (0.138) - this node is a cross-community bridge._
- **Why does `SyncManager` connect `Sync Manager & Folder Sync` to `Config & Settings`, `Backup Management`, `Safety Philosophy & Sync Principles`, `Logging & Main Entry`, `Robocopy Operations`, `Testing & Utilities`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Why does `RobocopyManager` connect `Robocopy Operations` to `Backup Management`, `Safety Philosophy & Sync Principles`, `Sync Manager & Folder Sync`, `Testing & Utilities`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `ConfigManager` (e.g. with `AppConfig` and `BackupSettings`) actually correct?**
  _`ConfigManager` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `SyncManager` (e.g. with `BackupManager` and `AppConfig`) actually correct?**
  _`SyncManager` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `RobocopyManager` (e.g. with `RobocopySettings` and `RobocopyExecutionError`) actually correct?**
  _`RobocopyManager` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `BackupManager` (e.g. with `BackupSettings` and `BackupError`) actually correct?**
  _`BackupManager` has 4 INFERRED edges - model-reasoned connections that need verification._