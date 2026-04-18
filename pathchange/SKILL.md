---
name: pathchange
description: Use when a project contains machine-specific Windows paths such as `C:\Users\oldname\...` and needs a safe portability pass. This skill is for auditing hard-coded paths, classifying repo-internal vs user-profile-dependent references, replacing document paths with `%USERPROFILE%`, preserving runtime safety with fallbacks in code, and validating that old paths are removed from documentation without breaking execution.
---

# Pathchange

## Overview

Use this skill for Windows path portability work across an existing project. It is designed for cases where files, scripts, prompts, READMEs, or specs still reference an old username or PC-specific absolute path.

Read [references/pathchange.md](references/pathchange.md) before editing when the request involves more than one file or when code and docs both need updates.

## Workflow

1. Audit first.
   Use `rg -n` or `rg -l` to find old paths before changing anything.

2. Split findings into two groups.
   Repo-internal references:
   These point back into the current repository. Prefer relative paths in code when possible, or compute the repo path dynamically.

   User-profile-dependent references:
   These point to `Downloads`, `Pictures`, `OneDrive`, or other home-directory locations. Prefer `%USERPROFILE%` in docs and environment-aware resolution in code.

3. Protect runtime behavior.
   Do not remove a working path fallback unless the new path is guaranteed to exist.
   For code, prefer this order:
   - explicit env var override
   - computed portable path
   - legacy path fallback if needed

4. Update docs and prompts separately from code.
   For `.md`, `.txt`, and similar narrative files, replace old `C:\Users\oldname\...` references with `%USERPROFILE%` forms when the path is outside the repo.
   If the docs intentionally describe the current repo root, `%USERPROFILE%\OneDrive\開発\...` is acceptable when the user wants a standardized form.

5. Validate after edits.
   Re-run `rg` to confirm old doc paths are gone.
   Run syntax or build checks for any edited code.
   If Git is available and the user asked for safety, commit before and after the refactor.

## Decision Rules

- Use relative paths for repo-local code references when the code can derive its own location safely.
- Use `%USERPROFILE%` for docs that mention `OneDrive`, `Downloads`, or `Pictures`.
- Use explicit env vars when a path is project-specific, environment-specific, or likely to vary across machines.
- Keep legacy fallbacks in code when removing them could break existing automation.
- Avoid mass replacement across source code unless the replacement rule is truly safe.

## Validation Checklist

- Old username path is no longer present in docs unless intentionally preserved as a fallback example.
- Updated code still compiles or passes a lightweight syntax check.
- New path rules are consistent across README, specs, prompts, and helper docs.
- Any reusable migration notes are captured in the project or in `references/pathchange.md`.
