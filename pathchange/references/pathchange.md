# Pathchange Specification

## Purpose

This reference defines a reusable workflow for replacing machine-specific Windows paths safely.

Use it when a project was moved to a new PC, the Windows username changed, or local absolute paths were copied into docs, prompts, scripts, or config.

## Target Patterns

Typical old patterns:

- `C:\Users\oldname\OneDrive\開発\ProjectName`
- `C:\Users\oldname\Downloads\...`
- `C:\Users\oldname\Pictures\...`
- `C:\Users\oldname\OneDrive\Obsidian in Onedrive 202602\...`

## Classification

### 1. Repo-internal path

Definition:
The path points back into the current repository.

Preferred fix:

- Code: derive from `__file__`, script directory, repo root, or relative path
- Docs: use either `%USERPROFILE%\...<repo>` when the user wants a standard Windows form, or relative links if the document is repo-centric

### 2. User-profile-dependent path

Definition:
The path points outside the repo but inside the Windows user profile.

Preferred fix:

- Docs: `%USERPROFILE%\...`
- Code: `USERPROFILE` or tool-specific env access
- Optional: add an explicit override env var before fallback logic

### 3. Project-specific external path

Definition:
The path points to a custom folder outside the repo and may vary by machine.

Preferred fix:

- Add a dedicated env var
- Keep legacy fallback only if immediate removal is risky

Examples:

- `LOCAL_ARTICLES_BASE`
- `BLOG_VERCEL_HOME`
- `AMAZON_TOP_IMAGE_LOCAL_OUTPUT_DIR`

## Safe Replacement Strategy

1. Save the current state first.
   If Git is available, commit or otherwise snapshot the current tree before edits.

2. Search before editing.
   Example:

   ```powershell
   rg -n "C:\\Users\\oldname" .
   ```

3. Update code conservatively.
   Prefer:

   ```text
   env override -> portable computed path -> legacy fallback
   ```

4. Update docs broadly.
   Docs are usually safe to standardize to `%USERPROFILE%`.

5. Validate.
   Example checks:

   ```powershell
   rg -n "C:\\Users\\oldname" README.md docs scripts
   ```

   ```powershell
   @'
   import py_compile
   py_compile.compile(r"some_script.py", doraise=True)
   '@ | python -
   ```

## Recommended Replacement Rules

For docs and prompts:

- `C:\Users\oldname\OneDrive\開発\ProjectName` -> `%USERPROFILE%\OneDrive\開発\ProjectName`
- `C:\Users\oldname\OneDrive\...` -> `%USERPROFILE%\OneDrive\...`
- `C:\Users\oldname\Downloads\...` -> `%USERPROFILE%\Downloads\...`
- `C:\Users\oldname\Pictures\...` -> `%USERPROFILE%\Pictures\...`

For Python code:

- `os.getenv("USERPROFILE")`
- `Path(os.getenv("USERPROFILE", ""))`
- `Path(__file__).resolve()`
- repo-root derivation from current file location

For JavaScript or Node:

- `process.env.USERPROFILE`

For PowerShell:

- `$env:USERPROFILE`

## Runtime Guardrails

- Do not replace a known-working hard-coded default with a non-existent path unless you add a fallback.
- Do not convert every absolute path to `%USERPROFILE%` inside source code blindly.
- Do not remove explicit command-line overrides.
- Do not rewrite generated output paths without checking downstream consumers.

## Deliverables

For a full pathchange task, try to leave behind:

- updated code with safe fallbacks
- updated docs and prompts
- a clean post-change grep result for old paths
- validation output
- a Git commit before and after, if requested

## Porting This Skill To Another Project

If another project needs the same workflow:

1. Copy the entire `pathchange` folder.
2. Place it under the global skills directory, typically `~/.codex/skills/`.
3. If desired, also keep a project copy in version control so the team can reuse and refine it.
