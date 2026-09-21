---
name: finishing-a-development-branch
description: "Verify tests, then present structured options to merge, PR, keep, or discard a completed development branch. Use when implementation is done and all tests pass."
version: 1.0.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, branch, merge, pull-request, cleanup, workflow-completion, integration]
    related_skills: [executing-plans, subagent-driven-development, verification-before-completion, plan]
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Detect environment → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass** — use `terminal` to run the project's test suite:

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Detect Environment

**Determine workspace state before presenting options** — use `terminal`:

```bash
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
GIT_DETACHED=$(git symbolic-ref --short HEAD 2>/dev/null && echo "no" || echo "yes")
```

This determines which menu to show and how cleanup works:

| State | Menu | Cleanup |
|-------|------|---------|
| Normal branch (not detached) | Standard 4 options | Standard branch cleanup |
| Detached HEAD | Reduced 3 options (no merge) | No cleanup (externally managed) |

> **Note:** Hermes Agent uses standard git branches, not worktrees. Skip worktree-specific detection and cleanup logic.

### Step 3: Determine Base Branch

```bash
# Try common base branches
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 4: Present Options

**Normal branch — present exactly these 4 options:**

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

**Detached HEAD — present exactly these 3 options:**

```
Implementation complete. You're on a detached HEAD (externally managed workspace).

1. Push as new branch and create a Pull Request
2. Keep as-is (I'll handle it later)
3. Discard this work

Which option?
```

**Don't add explanation** - keep options concise.

### Step 5: Execute Choice

#### Option 1: Merge Locally

```bash
# Merge first — verify success before removing anything
git checkout <base-branch>
git pull
git merge <feature-branch>

# Verify tests on merged result
<test command>
```

Only after merge succeeds and tests pass, delete the branch:

```bash
git branch -d <feature-branch>
```

#### Option 2: Push and Create PR

```bash
# Push branch
git push -u origin <feature-branch>
```

**Do NOT delete the branch** — user needs it alive to iterate on PR feedback.

#### Option 3: Keep As-Is

Report: "Keeping branch <name>."

**Don't clean up.**

#### Option 4: Discard

**Confirm first:**
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed, force-delete the branch:

```bash
git branch -D <feature-branch>
```

### Step 6: Cleanup Workspace

**Only runs for Options 1 and 4.** Options 2 and 3 always preserve the branch.

For standard git branches, cleanup is simply branch deletion (already done in Step 5). No worktree removal is needed.

If you are operating in an externally managed or containerized workspace, leave the workspace in place — the host environment owns it.

## Quick Reference

| Option | Merge | Push | Keep Branch | Delete Branch |
|--------|-------|------|-------------|----------------|
| 1. Merge locally | yes | - | - | yes |
| 2. Create PR | - | yes | yes | - |
| 3. Keep as-is | - | - | yes | - |
| 4. Discard | - | - | - | yes (force) |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Open-ended questions**
- **Problem:** "What should I do next?" is ambiguous
- **Fix:** Present exactly 4 structured options (or 3 for detached HEAD)

**Deleting branch before merge verified**
- **Problem:** Branch deleted but merge had conflicts or broken tests
- **Fix:** Merge first, verify tests on result, then delete branch

**No confirmation for discard**
- **Problem:** Accidentally delete work
- **Fix:** Require typed "discard" confirmation

## Red Flags

**Never:**
- Proceed with failing tests
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request
- Discard a branch before confirming merge success
- Run destructive git commands without CWD safety

**Always:**
- Verify tests before offering options
- Detect environment before presenting menu
- Present exactly 4 options (or 3 for detached HEAD)
- Get typed confirmation for Option 4
- `cd` to a known repo root before destructive operations

## Hermes Agent Integration

### Tools

- **`terminal`** — All git operations (checkout, merge, push, branch -d/-D), run the test suite, detect detached HEAD, determine base branch
- **`read_file`** — Read any changelog or release notes before merging
- **`search_files`** — Locate test configuration or build scripts if the test command is unknown

### With executing-plans

`executing-plans` and `subagent-driven-development` both hand off to this skill once all plan tasks are complete and verified. This skill is the terminal step of the implementation workflow:

```
plan → executing-plans → finishing-a-development-branch
plan → subagent-driven-development → finishing-a-development-branch
```

### With verification-before-completion

The test verification in Step 1 is a verification-before-completion checkpoint — never take a "tests pass" claim on faith; run the suite yourself via `terminal` and read the actual output. If a subagent did the implementation, verify its work independently before offering integration options.

### Branch model

Hermes Agent works with standard git branches on the user's local repository. It does not create or manage git worktrees. All branch lifecycle operations (create, merge, push, delete) use plain `git` commands via `terminal`. If you are running inside an externally managed or containerized workspace, leave workspace lifecycle to the host and only manage the branch itself.