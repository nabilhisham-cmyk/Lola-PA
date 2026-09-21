---
name: executing-plans
description: "Execute a written implementation plan in the current session with review checkpoints. Use when you have a plan to follow step-by-step with verifications."
version: 1.0.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [plan-execution, implementation, task-tracking, verification, workflow]
    related_skills: [plan, subagent-driven-development, finishing-a-development-branch, verification-before-completion]
---

# Executing Plans

## Overview

Load plan, review critically, execute all tasks, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** If subagent dispatch is available (it is in Hermes Agent via `delegate_task`), prefer `subagent-driven-development` for higher quality through fresh isolated context per task. Use this skill when tasks are tightly coupled and must be executed inline in the current session.

## The Process

### Step 1: Load and Review Plan

1. Read plan file with `read_file`
2. Review critically - identify any questions or concerns about the plan
3. If concerns: Raise them with your human partner before starting
4. If no concerns: Create todos for the plan items and proceed

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified — use `terminal` to execute test/build commands
4. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the finishing-a-development-branch skill to complete this work."
- **REQUIRED SUB-SKILL:** Use `finishing-a-development-branch`
- Follow that skill to verify tests, present options, execute choice

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember

- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent

## Hermes Agent Integration

### Tools

- **`read_file`** — Load the plan file and any referenced source files
- **`search_files`** — Find files referenced by the plan by name or content
- **`terminal`** — Run verifications (tests, builds, lint) and git operations
- **`write_file`** / **`patch`** — Apply changes specified by each plan step
- **`todo`** — Track task progress through the plan (in_progress → completed)

### With plan skill

The `plan` skill creates the implementation plan. This skill executes it:

```
brainstorming → plan → executing-plans → finishing-a-development-branch
```

### With subagent-driven-development

When tasks are mostly independent, prefer `subagent-driven-development` — it dispatches a fresh subagent per task with review after each, yielding higher quality than inline execution. This skill is for tightly coupled tasks that must run in the current session's shared context.

### With finishing-a-development-branch

After all tasks complete and verifications pass, this skill hands off to `finishing-a-development-branch` to verify the full suite, present integration options (merge / PR / keep / discard), and clean up the branch.

### With verification-before-completion

Every task's "done" claim must be independently verified before marking it completed — run the plan's specified verification command via `terminal` and confirm it actually passes.