# CLAUDE.md

# OneDrive PC Sync — Claude Code Instructions

These instructions apply to the entire repository.

---

# Primary Goal

Your objective is to implement high-quality, production-ready code while preserving the existing architecture.

Always prefer correctness, maintainability and consistency over speed.

Never make assumptions about the project structure without first consulting the project documentation.

---

# PROJECT_MEMORY.md is the Source of Truth

`PROJECT_MEMORY.md` is the authoritative documentation for this repository.

Before implementing any change you MUST inspect it.

Whenever you implement a feature, fix a bug, refactor code, rename files, add configuration, change synchronization behavior or modify the architecture, you MUST update `PROJECT_MEMORY.md`.

A task is NOT complete until the documentation has been updated.

---

# Mandatory Development Workflow

For every task follow this exact workflow.

1. Read `PROJECT_MEMORY.md`.
2. Open `graphify-out/wiki/index.md`.
3. Query Graphify to understand the relevant architecture.
4. Identify only the files involved.
5. Read only those files.
6. Implement the requested changes.
7. Verify that the implementation is correct.
8. Update `PROJECT_MEMORY.md`.
9. Verify that the documentation matches the implementation.
10. Only then consider the task complete.

Never skip any step.

---

# Graphify is Mandatory

This repository uses Graphify as its primary knowledge source.

Graphify exists specifically to avoid scanning the entire repository.

Always use it first.

## Rules

- Always query the knowledge graph first.
- Never start by searching the repository.
- Never recursively inspect the project.
- Never perform broad searches if Graphify can answer the question.
- Use `graphify-out/wiki/index.md` as the entry point.
- Follow Graphify links before opening any source file.
- Use Graphify to discover:
  - execution flow
  - architecture
  - dependencies
  - modules
  - classes
  - functions
  - configuration
  - scheduled tasks
  - synchronization flow
- Open only the files Graphify identifies as relevant.
- Read the minimum amount of source code necessary.
- If Graphify is incomplete, then read the missing source files.
- If Graphify disagrees with the source code, trust the source code and update the documentation if appropriate.

---

# Repository Search Policy

Searching the repository should be the exception, not the default.

Do NOT:

- recursively search the project
- grep the entire repository
- open dozens of files
- inspect unrelated directories
- read files "just in case"

Instead:

1. Query Graphify.
2. Locate the relevant component.
3. Open only those files.

Repository-wide searches are allowed ONLY if I explicitly request them.

Examples:

Allowed:

- "Search the repository"
- "Read the implementation"
- "Ignore Graphify"
- "Inspect the whole project"

Otherwise always use Graphify.

---

# Source File Reading Policy

Only read raw source files after Graphify has identified them.

Do not manually browse folders.

Do not inspect unrelated files.

Read the smallest possible number of files.

---

# PROJECT_MEMORY Update Rules

Update `PROJECT_MEMORY.md` whenever you:

- add files
- remove files
- rename files
- rename modules
- rename classes
- rename scripts
- add dependencies
- remove dependencies
- modify configuration
- change synchronization logic
- change monitoring
- change backups
- change scheduled tasks
- modify startup behavior
- modify shutdown behavior
- change CLI arguments
- change execution flow
- modify architecture
- add services
- change project structure

Do NOT update it for:

- formatting
- comments
- typo fixes
- whitespace
- trivial refactoring

---

# How to Update PROJECT_MEMORY.md

Modify only the sections affected.

Do NOT rewrite the entire document.

Keep the existing formatting.

Keep the same writing style.

Update the **Last updated** field.

Update sections only when necessary, including:

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

Create new sections only when absolutely necessary.

If no update is needed, explicitly explain why.

---

# Code Quality Standards

Always produce production-ready code.

Code should be:

- modular
- readable
- documented where appropriate
- maintainable
- consistent with the existing architecture

Avoid:

- duplicated logic
- unnecessary abstractions
- dead code
- magic values
- unused imports

Prefer extending existing systems over introducing new ones.

---

# Bug Fixes

When fixing a bug:

1. Use Graphify to locate the execution path.
2. Understand the root cause.
3. Fix the cause, not only the symptom.
4. Verify that existing behavior is preserved.
5. Update documentation if behavior changed.

---

# Feature Development

When implementing a feature:

1. Inspect the architecture with Graphify.
2. Reuse existing systems whenever possible.
3. Keep changes localized.
4. Preserve backward compatibility unless instructed otherwise.
5. Update PROJECT_MEMORY.

---

# Refactoring

Refactoring should never change observable behavior unless explicitly requested.

After refactoring:

- verify imports
- verify references
- verify execution flow
- update PROJECT_MEMORY if architecture changed

---

# Documentation Consistency

Documentation must always reflect the implementation.

If code changes:

- update PROJECT_MEMORY

If documentation is outdated:

- update it before finishing the task

Implementation and documentation must never diverge.

---

# Completion Checklist

A task is NOT complete until all of the following are true:

- implementation finished
- code compiles (if applicable)
- existing behavior preserved
- new files documented
- changed behavior documented
- PROJECT_MEMORY updated
- PROJECT_MEMORY matches the implementation
- Graphify workflow respected

If PROJECT_MEMORY was intentionally left unchanged, explicitly explain why.

Only then is the task considered complete.