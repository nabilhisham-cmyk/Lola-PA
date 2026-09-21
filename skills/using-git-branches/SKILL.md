---
name: using-git-branches
description: Use when starting feature work that needs isolation from main, or before executing implementation plans - ensures work happens on a dedicated feature branch separate from main/master
version: 1.0.0
author: 'Hermes Agent (adapted from obra/superpowers)'
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, branches, workflow, isolation, version-control]
    related_skills:
      - systematic-debugging
      - test-driven-development
      - receiving-code-review
---

# Using Git Branches

## Overview

Ensure feature work happens on an isolated branch, separate from `main`/`master`. This protects the stable branch from incomplete changes, makes review easier, and simplifies cleanup after merge.

**Core principle:** Detect existing isolation first. Then create a feature branch. Never commit feature work directly to `main`.

**Announce at start:** "I'm using the using-git-branches skill to set up an isolated branch."

## Step 0: Detect Existing Isolation

**Before creating anything, check if you are already on a feature branch.**

```bash
BRANCH=$(git branch --show-current)
```

**Interpretation:**

| Branch state | Meaning | Action |
|---|---|---|
| On `main` or `master` | Not isolated — need a feature branch | Proceed to Step 1 |
| On a feature branch (e.g. `feature/auth`) | Already isolated | Skip to Step 2 (Project Setup) |
| Detached HEAD | Externally managed checkout | Proceed to Step 1, branch creation needed |

**If already on a feature branch:** Report and skip to Step 2.
- "Already on isolated branch `<name>`. Proceeding with project setup."

**If on `main`/`master`:** Continue to Step 1. Has the user indicated a branch naming preference in your instructions? If not, ask:

> "Would you like me to create a feature branch for this work? It keeps `main` stable while we iterate."

Honor any existing declared preference without asking. If the user declines, work in place and skip to Step 2 — but warn that committing to `main` risks polluting the stable branch.

## Step 1: Create Feature Branch

### 1a. Branch Naming

Follow this priority order. Explicit user preference always beats observed repo state.

1. **Check your instructions for a declared branch-naming convention.** If the user has specified one (e.g. `feature/`, `fix/`, `chore/` prefixes), use it without asking.

2. **Check existing branch patterns:**
   ```bash
   git branch --list 'feature/*' | head -5
   git branch --list 'fix/*' | head -5
   ```
   If the repo already uses a convention, match it.

3. **If there is no other guidance**, default to `feature/<short-description>`:
   ```bash
   git checkout -b feature/add-auth-redirects
   ```

### 1b. Baseline Safety

**Before creating the branch, ensure the working tree is clean:**

```bash
git status --porcelain
```

| State | Action |
|---|---|
| Clean working tree | Create branch immediately |
| Uncommitted changes (tracked files) | `git stash` first, create branch, then `git stash pop` after |
| Untracked files | Safe to carry over; create branch in place |

**Why stash first:** Creating a branch with `git checkout -b` carries uncommitted changes to the new branch. If those changes belong on `main`, stash and reapply after switching back. If they belong on the feature, this is fine.

### 1c. Create the Branch

```bash
# Stash if needed (see 1b)
git stash  # only if working tree is dirty

# Create and switch to the feature branch
git checkout -b feature/<short-description>

# Restore stashed changes if any
git stash pop 2>/dev/null  # only if you stashed
```

**Sandbox fallback:** If `git checkout -b` fails with a permission error (sandbox denial), tell the user the sandbox blocked branch creation and you're working in the current branch instead. Then run setup and baseline tests in place.

## Step 2: Project Setup

Auto-detect and run appropriate setup:

```bash
# Node.js
if [ -f package.json ]; then npm install; fi

# Rust
if [ -f Cargo.toml ]; then cargo build; fi

# Python
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ]; then poetry install; fi

# Go
if [ -f go.mod ]; then go mod download; fi
```

## Step 3: Verify Clean Baseline

Run tests to ensure the branch starts clean:

```bash
# Use project-appropriate command
npm test / cargo test / pytest / go test ./...
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

### Report

```
Feature branch: feature/<name> (created from <parent>)
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Step 4: Committing Feature Work

As you implement, commit logically grouped changes to the feature branch:

```bash
git add <files>
git commit -m "<descriptive message>"
```

**Keep commits focused:** One logical change per commit. This makes review and rollback easier.

**Do NOT merge to `main` yet.** The feature branch stays separate until work is complete and reviewed.

## Step 5: Cleanup After Merge

Once the feature branch has been merged to `main` (via PR, fast-forward, or merge):

```bash
# Switch back to main and pull latest
git checkout main
git pull origin main

# Delete the merged feature branch (local)
git branch -d feature/<name>

# Delete the remote branch if it exists
git push origin --delete feature/<name> 2>/dev/null
```

**Why delete:** Stale branches accumulate and obscure active work. `-d` (lowercase) only deletes fully merged branches, so it's safe.

**If the branch was squash-merged** (not a true merge): `git branch -d` may refuse. Use `-D` only after confirming the work is in `main`:
```bash
git log main --oneline | grep "<feature description>"
# If present, safe to force-delete:
git branch -D feature/<name>
```

## Quick Reference

| Situation | Action |
|-----------|--------|
| Already on a feature branch | Skip creation (Step 0) |
| On `main`/`master` | Create feature branch (Step 1) |
| Detached HEAD | Create branch (Step 1) |
| Dirty working tree | `git stash` → create branch → `git stash pop` |
| Branch-naming convention in instructions | Use it without asking |
| Existing `feature/*` branches | Match the convention |
| No convention found | Default `feature/<short-description>` |
| Permission error on branch creation | Sandbox fallback, work in place |
| Tests fail during baseline | Report failures + ask |
| No package.json/Cargo.toml | Skip dependency install |
| Feature merged to `main` | `git branch -d` to clean up |
| Squash-merged (branch -d refuses) | Verify in `main`, then `git branch -D` |
| Remote branch exists post-merge | `git push origin --delete` |

## Common Mistakes

### Committing directly to `main`

- **Problem:** Feature work on `main` pollutes the stable branch and makes rollback difficult
- **Fix:** Always create a feature branch first (Step 0 detection, Step 1 creation)

### Skipping detection

- **Problem:** Creating a nested branch or rebasing when already isolated
- **Fix:** Always run Step 0 before creating anything

### Carrying dirty changes across branches

- **Problem:** Uncommitted changes belong on `main` but get carried to the feature branch
- **Fix:** `git stash` before creating the branch, reapply on the correct branch

### Inconsistent branch naming

- **Problem:** Creates inconsistency, violates project conventions
- **Fix:** Follow priority: explicit instructions > existing branch patterns > default `feature/<name>`

### Not cleaning up merged branches

- **Problem:** Stale branches accumulate, obscure active work
- **Fix:** After merge, delete local and remote feature branches (Step 5)

### Proceeding with failing tests

- **Problem:** Can't distinguish new bugs from pre-existing issues
- **Fix:** Report failures, get explicit permission to proceed

## Red Flags

**Never:**
- Commit feature work directly to `main`/`master`
- Create a branch without checking if you're already on one
- Skip baseline test verification
- Proceed with failing tests without asking
- Leave merged branches lying around (clean them up)
- Force-delete (`-D`) a branch without confirming the work is in `main`

**Always:**
- Run Step 0 detection first
- Follow branch-naming priority: explicit instructions > existing patterns > default
- Stash dirty changes before switching branches (when needed)
- Auto-detect and run project setup
- Verify clean test baseline
- Clean up branches after merge

## Hermes Agent Integration

Use Hermes Agent tools to manage git branches:

- **read_file** — read `.gitignore`, branch-naming configs, or CI workflow files to understand conventions
- **search_files** — search for existing branch patterns or feature documentation
- **write_file** — update `.gitignore` or branch documentation if needed
- **patch** — targeted edits to config files (e.g., CI branch protection rules)
- **delegate_task()** — dispatch a subagent to run the test suite and verify the baseline is clean: `delegate_task(prompt="Run the project's test suite and report pass/fail counts.", context={"branch": "feature/auth"})`

**Branch verification workflow:**
1. Use `search_files` to find existing branch-naming patterns in the repo
2. Create the branch with terminal commands
3. Use `delegate_task()` to verify the test baseline in the new branch
4. After implementation, use `delegate_task()` again to confirm no regressions before merging

## The Bottom Line

**Isolation first. Always.**

Detect existing isolation. Create a feature branch if needed. Verify a clean test baseline. Implement. Clean up after merge.

Never pollute `main`. Never skip detection. Never leave stale branches.