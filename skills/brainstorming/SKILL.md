---
name: brainstorming
description: "Collaborative design before implementation: explore intent, propose approaches, get approval before coding."
version: 1.0.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [brainstorming, design, planning, requirements, spec, approval]
    related_skills: [plan, subagent-driven-development, writing-skills]
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design and get user approval.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design and the user has approved it. This applies to EVERY project regardless of perceived simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility, a config change — all of them. "Simple" projects are where unexamined assumptions cause the most wasted work. The design can be short (a few sentences for truly simple projects), but you MUST present it and get approval.

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** — check files, docs, recent commits
2. **Ask clarifying questions** — one at a time, understand purpose/constraints/success criteria
3. **Propose 2-3 approaches** — with trade-offs and your recommendation
4. **Present design** — in sections scaled to their complexity, get user approval after each section
5. **Write design doc** — save to `.hermes/plans/YYYY-MM-DD-<topic>-design.md` and commit
6. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope
7. **User reviews written spec** — ask user to review the spec file before proceeding
8. **Transition to implementation** — invoke the `plan` skill to create implementation plan

## Process Flow

### Step 1: Explore Project Context

Before asking anything, investigate the current state:

- Use `search_files` to find relevant existing code and patterns
- Use `read_file` to check key files (README, config, package manifests)
- Use `terminal` to check `git log --oneline -10` for recent activity
- Note the tech stack, conventions, and any constraints

### Step 2: Ask Clarifying Questions

Ask ONE question at a time. Wait for the answer before asking the next.

Good questions:
- "What problem does this solve for you?"
- "Who will use this and how?"
- "What's the expected output format?"
- "Are there existing patterns in this codebase I should follow?"
- "What happens if we don't build this?"

Bad questions (too vague):
- "What do you want?" (too open)
- "Tell me everything about the project" (too broad)

### Step 3: Propose 2-3 Approaches

After understanding the idea, present 2-3 approaches with trade-offs:

```
## Approach A: [name]
- Pros: ...
- Cons: ...
- Effort: ...

## Approach B: [name]
- Pros: ...
- Cons: ...
- Effort: ...

## Recommendation
I recommend [A/B/C] because [reasoning].
```

Present approaches as a single block, not one at a time. The user needs to compare them side by side.

### Step 4: Present Design

Scale the design to the complexity of the project:

**For simple projects** (1-2 files, straightforward logic):
- 3-5 sentences describing what you'll build, the approach, and key files

**For medium projects** (3-10 files, some complexity):
- Goal statement
- File structure
- Key interfaces/functions
- Testing approach

**For complex projects** (multiple subsystems):
- Architecture overview
- Component breakdown
- File structure
- Interface definitions
- Testing strategy
- Migration/deployment plan
- Risks and mitigations

Present in sections. Get approval after each section. Don't dump the whole design at once.

### Step 5: Write Design Doc

Save the approved design to:

```
.hermes/plans/YYYY-MM-DD-<topic>-design.md
```

Use `write_file` to create the file. Commit it with `terminal`:

```bash
git add .hermes/plans/YYYY-MM-DD-<topic>-design.md
git commit -m "docs: design spec for <topic>"
```

### Step 6: Spec Self-Review

Check the written spec for:
- [ ] No placeholder text ("TODO", "TBD", "...")
- [ ] No contradictions between sections
- [ ] No ambiguity that a junior developer couldn't resolve
- [ ] Scope is appropriate — not too broad, not too narrow
- [ ] All acronyms defined
- [ ] File paths are specific, not "some file"

Fix issues inline before asking the user to review.

### Step 7: User Reviews Written Spec

Tell the user: "I've written the design spec to `.hermes/plans/YYYY-MM-DD-<topic>-design.md`. Please review it and let me know if anything needs to change before I create the implementation plan."

Wait for approval. Do NOT proceed to planning until the user confirms.

### Step 8: Transition to Implementation

Once the user approves the spec, invoke the `plan` skill to create a detailed implementation plan from the design.

## When to Skip Brainstorming

Skip this skill ONLY when:
- The user explicitly says "don't brainstorm, just build it"
- The task is a direct fix to a known issue (e.g., "change the button color to blue")
- The user provides a complete spec already

If the user says "just do it" — respect that. Note that you skipped brainstorming and proceed directly.

## Common Failures

| Failure | Fix |
|---------|-----|
| Asking too many questions at once | One at a time. Always. |
| Skipping to implementation without approval | HARD-GATE violation. Stop. Present design. |
| Design is too vague for implementation | Add file paths, function signatures, test targets |
| Design is too detailed for a simple task | Scale to complexity. Simple tasks get simple designs. |
| Not checking existing code | Always explore context first (Step 1) |

## Hermes Agent Integration

### Tools

- **`search_files`** — Find existing patterns, similar code, conventions
- **`read_file`** — Read key project files for context
- **`terminal`** — Check git history, run project inspection commands
- **`write_file`** — Write the design spec document
- **`delegate_task`** — For large projects, dispatch a research subagent to explore the codebase in parallel while you ask questions

### With plan skill

Brainstorming produces the design spec. The `plan` skill consumes it to produce an implementation plan. The two skills chain:

```
brainstorming → design spec → plan → implementation plan → subagent-driven-development → code
```

### With writing-skills

When the "skill" is a new Hermes skill itself (not application code), use `writing-skills` instead of `plan` after brainstorming — it has TDD for skills specifically.