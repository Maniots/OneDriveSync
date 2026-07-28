# Claude Code Project Instructions

## PROJECT_MEMORY.md is the source of truth

`PROJECT_MEMORY.md` is the authoritative documentation for this repository.

Whenever you implement a feature, fix a bug, refactor behavior, add/remove files, or modify the architecture, you MUST update `PROJECT_MEMORY.md` before considering the task complete.

## When to update it

Update the memory whenever you:

- add or remove files
- modify existing functionality
- introduce new configuration options
- change execution flow
- modify scheduled tasks
- modify monitoring
- modify backup behavior
- modify synchronization logic
- add dependencies
- rename classes, modules or scripts
- change CLI arguments
- change project structure

Pure formatting, comments, or trivial refactors do not require updates.

## How to update it

Only modify the sections affected by your changes.

Never rewrite the entire document.

Keep the structure, formatting and writing style consistent with the existing document.

Update the "Last updated" field.

If necessary, update:

- Project Overview
- Architecture
- Configuration
- Safety Architecture
- Sync Flow
- Backup System
- Scheduled Tasks
- Entry Point
- Key Files
- Gotchas & Invariants
- Future Work
- Recent Changes

Add new sections only if absolutely necessary.

## Completion Checklist

A task is NOT complete until all of the following are true:

- The implementation is finished.
- The code compiles (if applicable).
- Existing behavior has not been unintentionally broken.
- New files are documented.
- Changed behavior is documented.
- PROJECT_MEMORY.md has been updated.
- PROJECT_MEMORY.md accurately reflects the current implementation.

If PROJECT_MEMORY.md was intentionally left unchanged, explicitly explain why.

## Workflow

For every implementation:

1. Inspect PROJECT_MEMORY.md.
2. Implement the requested changes.
3. Update PROJECT_MEMORY.md.
4. Verify that the documentation matches the implementation.
5. Only then consider the task complete.

Never wait for the user to explicitly request a PROJECT_MEMORY.md update.
Always treat it as part of the implementation.