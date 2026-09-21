---
name: subagent-driven-development
description: "Execute implementation plans by dispatching a fresh subagent per task, with review after each and a broad final review."
version: 1.0.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [subagents, delegation, plan-execution, task-orchestration, review, implementation]
    related_skills: [plan, brainstorming, requesting-code-review, verification-before-completion]
---

# Subagent-Driven Development

Execute plan by dispatching a fresh implementer subagent per task, a task review (spec compliance + code quality) after each, and a broad whole-branch review at the end.

**Why subagents:** You delegate tasks to specialized agents with isolated context. By precisely crafting their instructions and context, you ensure they stay focused and succeed at their task. They should never inherit your session's context or history — you construct exactly what they need. This also preserves your own context for coordination work.

**Core principle:** Fresh subagent per task + task review (spec + quality) + broad final review = high quality, fast iteration

**Continuous execution:** Do not pause to check in with your human partner between tasks. Execute all tasks from the plan without stopping. The only reasons to stop are: BLOCKED status you cannot resolve, ambiguity that genuinely prevents progress, or all tasks complete.

## When to Use

Use when:
- You have an implementation plan (from the `plan` skill or written manually)
- Tasks are mostly independent (one task's output doesn't determine the next task's approach)
- You're staying in the current session

Don't use when:
- Tasks are tightly coupled — use `executing-plans` or implement inline
- No plan exists — use `brainstorming` then `plan` first
- Single small task — just do it inline

## The Process

### Step 1: Load Plan

Read the plan file. Create todos for all tasks. Understand the task order and dependencies.

### Step 2: Per-Task Execution

For each task in the plan:

#### 2a. Dispatch Implementer Subagent

Use `delegate_task` with a precisely crafted goal:

```python
delegate_task(
    goal="""Implement Task N from the plan.

    ## Task Description
    [Copy the exact task description from the plan]

    ## Files to Create/Modify
    [List specific files from the plan]

    ## Requirements
    [List acceptance criteria from the plan]

    ## Context
    [Provide only what's needed for THIS task — not your session history]
    - Project: [name]
    - Tech stack: [stack]
    - Conventions: [key conventions to follow]

    ## Constraints
    - Follow TDD: write failing test first, implement, verify
    - Do NOT modify files outside the scope of this task
    - Commit your work with: git commit -m "task N: [description]"
    - Run tests and verify they pass before finishing
    """,
    context="[Any code snippets, interfaces, or patterns the subagent needs]",
    toolsets=['terminal', 'file', 'web']  # Only what's needed
)
```

#### 2b. If Implementer Asks Questions

The subagent may ask clarifying questions via its return value. Answer them and re-dispatch with the answers included. Do NOT do the work yourself — your job is coordination, not implementation.

#### 2c. Task Review

After the implementer finishes, dispatch a task reviewer:

```python
delegate_task(
    goal="""Review Task N implementation.

    ## What Was Built
    [Summary from implementer]

    ## Requirements (from plan)
    [Copy task requirements]

    ## Review Checklist
    1. Does the implementation match the plan's requirements?
    2. Are tests written and passing?
    3. Is the code clean and following project conventions?
    4. Are there any bugs or edge cases missed?
    5. Is the commit message appropriate?

    ## Output Format
    - Spec compliance: PASS/FAIL (with details)
    - Code quality: PASS/FAIL (with details)
    - Issues found: [list, or "none"]
    - Recommendation: APPROVE / FIX_REQUIRED (with specific fixes if needed)
    """,
    context="[The diff or file changes to review]",
    toolsets=['terminal', 'file']
)
```

#### 2d. Handle Review Results

- **APPROVE:** Move to the next task
- **FIX_REQUIRED:** Re-dispatch the implementer with the review feedback and the specific fixes needed
- Repeat review cycle until APPROVE

### Step 3: Broad Final Review

After all tasks complete, dispatch a comprehensive reviewer for the entire branch:

```python
delegate_task(
    goal="""Comprehensive branch review for [project name].

    ## Branch
    [branch name]

    ## Base
    [base commit SHA]

    ## What Was Built
    [Summary of all tasks from the plan]

    ## Review Scope
    - All commits in the branch (git log [base]..HEAD)
    - Full diff (git diff [base]..HEAD)
    - Test suite passing
    - Integration between tasks (do the pieces fit together?)
    - No regressions in existing functionality

    ## Output
    - Overall assessment: READY_TO_MERGE / NEEDS_FIXES
    - Critical issues (must fix before merge)
    - Important issues (should fix before merge)
    - Minor issues (can fix later)
    - Strengths
    """,
    toolsets=['terminal', 'file']
)
```

### Step 4: Handle Final Review

- Fix critical issues by dispatching targeted subagents
- Fix important issues if time permits
- Note minor issues for follow-up
- Once critical issues are resolved, inform the user the branch is ready

## Narration Rule

Between tool calls, narrate at most one short line. The ledger (todos) and tool results carry the record. Don't write paragraphs of explanation between each dispatch.

## When to Stop

**STOP executing immediately when:**
- Hit a blocker you cannot resolve (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing progress
- Ambiguity that genuinely prevents progress
- All tasks complete

**Do NOT stop for:**
- "Should I continue?" prompts — the user asked you to execute, execute
- Progress summaries — the todos track progress
- Checking in between tasks — keep going

## Delegation Patterns

### Independent Tasks (Parallel)

When tasks have no dependencies, dispatch them in a batch:

```python
delegate_task(tasks=[
    {"goal": "Task A...", "context": "...", "toolsets": ["terminal", "file"]},
    {"goal": "Task B...", "context": "...", "toolsets": ["terminal", "file"]},
    {"goal": "Task C...", "context": "...", "toolsets": ["terminal", "file"]},
])
```

### Dependent Tasks (Sequential)

When Task B depends on Task A's output, wait for A to complete and review before dispatching B. Include A's output in B's context.

### Background Dispatch

For long-running tasks, use `background=true`:

```python
delegate_task(
    goal="Long-running task...",
    background=True,
    ...
)
```

You and the user keep working while it runs. The result re-enters the conversation when done.

## Hermes Agent Integration

### Tools

- **`delegate_task`** — Dispatch implementer and reviewer subagents
- **`terminal`** — Check git state, run tests, verify changes
- **`read_file`** / **`search_files`** — Gather context for subagent instructions
- **`todo`** — Track task progress through the plan

### With plan skill

The `plan` skill creates the implementation plan. This skill executes it:

```
brainstorming → plan → subagent-driven-development → requesting-code-review → commit
```

### With requesting-code-review

After all tasks complete and the broad review passes, use `requesting-code-review` for a final automated verification pass before committing.

### With verification-before-completion

Every subagent's "done" claim must be independently verified:

```bash
# Don't trust the subagent — check
git diff --stat
pytest tests/ -q
npm run build
```