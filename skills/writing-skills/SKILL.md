---
name: writing-skills
description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
version: 1.0.0
author: 'Hermes Agent (adapted from obra/superpowers)'
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skills, documentation, testing, tdd, process]
    related_skills:
      - systematic-debugging
      - test-driven-development
      - receiving-code-review
---

# Writing Skills

## Overview

**Writing skills IS Test-Driven Development applied to process documentation.**

You write test cases (pressure scenarios with delegated subagents), watch them fail (baseline behavior), write the skill (documentation), watch tests pass (agents comply), and refactor (close loopholes).

**Core principle:** If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing.

**REQUIRED BACKGROUND:** You MUST understand the `test-driven-development` skill before using this. That skill defines the fundamental RED-GREEN-REFACTOR cycle. This skill adapts TDD to documentation.

## What is a Skill?

A **skill** is a reference guide for proven techniques, patterns, or tools. Skills help future agents find and apply effective approaches.

**Skills are:** Reusable techniques, patterns, tools, reference guides

**Skills are NOT:** Narratives about how you solved a problem once

## TDD Mapping for Skills

| TDD Concept | Skill Creation |
|-------------|----------------|
| **Test case** | Pressure scenario with delegated subagent |
| **Production code** | Skill document (SKILL.md) |
| **Test fails (RED)** | Agent violates rule without skill (baseline) |
| **Test passes (GREEN)** | Agent complies with skill present |
| **Refactor** | Close loopholes while maintaining compliance |
| **Write test first** | Run baseline scenario BEFORE writing skill |
| **Watch it fail** | Document exact rationalizations agent uses |
| **Minimal code** | Write skill addressing those specific violations |
| **Watch it pass** | Verify agent now complies |
| **Refactor cycle** | Find new rationalizations → plug → re-verify |

## When to Create a Skill

**Create when:** Technique wasn't intuitively obvious; you'd reference this across projects; pattern applies broadly; others would benefit.

**Don't create for:** One-off solutions; standard practices well-documented elsewhere; project-specific conventions; mechanical constraints (automate those instead).

## Skill Types

- **Technique** — Concrete method with steps to follow (condition-based-waiting, root-cause-tracing)
- **Pattern** — Way of thinking about problems (flatten-with-flags, test-invariants)
- **Reference** — API docs, syntax guides, tool documentation

## Directory Structure

```
skills/
  skill-name/
    SKILL.md              # Main reference (required)
    supporting-file.*     # Only if needed (heavy reference or reusable tools)
```

**Flat namespace** — all skills in one searchable namespace. Separate files for heavy reference (100+ lines) or reusable tools. Keep everything else inline.

## SKILL.md Structure

**Frontmatter (YAML):** Required fields `name` and `description` (max 1024 chars total). `name`: letters, numbers, hyphens only. `description`: third-person, describes ONLY when to use (NOT what it does), starts with "Use when...", under 500 chars if possible.

```markdown
---
name: skill-name-with-hyphens
description: Use when [specific triggering conditions and symptoms]
---
# Skill Name
## Overview — Core principle in 1-2 sentences
## When to Use — Symptoms and use cases; when NOT to use
## Core Pattern — Before/after code comparison
## Quick Reference — Table or bullets for scanning
## Common Mistakes — What goes wrong + fixes
```

## Skill Discovery Optimization (SDO)

**Critical:** Future agents need to FIND your skill.

### Description = When to Use, NOT What the Skill Does

Testing revealed that when a description summarizes the skill's workflow, an agent may follow the description instead of reading the full skill content. A description saying "code review between tasks" caused an agent to do ONE review, even though the skill's flowchart clearly showed TWO reviews.

**The trap:** Descriptions that summarize workflow create a shortcut agents will take. The skill body becomes documentation agents skip.

```yaml
# ❌ BAD: Summarizes workflow
description: Use when executing plans - dispatches subagent per task with code review between tasks
# ✅ GOOD: Just triggering conditions
description: Use when executing implementation plans with independent tasks in the current session
```

### Other SDO Factors

- **Keyword coverage:** Use error messages, symptoms, synonyms, and tool names agents would search for.
- **Descriptive naming:** Active voice, verb-first (`creating-skills` not `skill-creation`).
- **Cross-referencing:** Use skill name with explicit requirement markers: `**REQUIRED SUB-SKILL:** Use test-driven-development`. No `@` links (force-loads, burns context).

## The Iron Law (Same as TDD)

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

This applies to NEW skills AND EDITS to existing skills.

Write skill before testing? Delete it. Start over. Edit skill without testing? Same violation.

**No exceptions:** Not for "simple additions", "just adding a section", "documentation updates", or keeping untested changes as "reference". Delete means delete.

## Match the Form to the Failure

| Baseline failure | Right form | Wrong form |
|---|---|---|
| Skips/violates a rule under pressure | Prohibition + rationalization table + red flags | Soft guidance ("prefer...") |
| Output has wrong shape (bloated, buried) | Positive recipe: state what the output IS — parts, in order | Prohibition list ("don't restate") |
| Omits a required element | Structural: REQUIRED field or slot in template | Prose reminders |
| Behavior depends on a condition | Conditional on observable predicate | Unconditional rule + exemptions |

**Rules:** No nuance clauses ("don't X unless it matters" reopens negotiation). Exemption clauses don't scope ("doesn't apply to code blocks" still suppresses them).

## Bulletproofing Against Rationalization

For discipline skills, close every loophole explicitly. Address "spirit vs letter" arguments early: `**Violating the letter of the rules is violating the spirit of the rules.**`

Build a rationalization table from baseline testing (every excuse agents make). Create a red flags list for self-checking.

## RED-GREEN-REFACTOR for Skills

### RED: Write Failing Test (Baseline)
Run pressure scenario with delegated subagent WITHOUT the skill. Document: what choices did they make? What rationalizations (verbatim)? Which pressures triggered violations?

### GREEN: Write Minimal Skill
Write skill addressing those specific rationalizations. Run same scenarios WITH skill. Agent should now comply.

### REFACTOR: Close Loopholes
Agent found new rationalization? Add explicit counter. Re-test until bulletproof.

### Micro-Test Wording First
Full scenarios are slow. Verify wording first: one fresh-context sample per call; always include a no-guidance control; 5+ reps per variant; manually read every flagged match; variance is a metric (convergence = wording binds).

## Testing All Skill Types

| Skill type | Test with | Success criteria |
|---|---|---|
| Discipline-enforcing (rules) | Academic questions, pressure scenarios, combined pressures | Agent follows rule under max pressure |
| Technique (how-to) | Application scenarios, edge cases, missing-info tests | Agent applies technique to new scenario |
| Pattern (mental models) | Recognition, application, counter-examples | Agent identifies when/how to apply |
| Reference (docs/APIs) | Retrieval, application, gap testing | Agent finds and applies info correctly |

## Common Rationalizations for Skipping Testing

| Excuse | Reality |
|--------|---------|
| "Skill is obviously clear" | Clear to you ≠ clear to other agents. Test it. |
| "It's just a reference" | References can have gaps. Test retrieval. |
| "Testing is overkill" | Untested skills have issues. 15 min saves hours. |
| "I'll test if problems emerge" | Test BEFORE deploying, not after. |

**All of these mean: Test before deploying. No exceptions.**

## Anti-Patterns

- ❌ **Narrative example** — too specific, not reusable
- ❌ **Multi-language dilution** — mediocre quality, maintenance burden
- ❌ **Code in flowcharts** — can't copy-paste
- ❌ **Generic labels** (helper1, step3) — labels need semantic meaning

## STOP: Before Moving to Next Skill

After writing ANY skill, you MUST STOP and complete the deployment process. Do NOT create multiple skills in batch without testing each. Deploying untested skills = deploying untested code.

## Skill Creation Checklist (TDD Adapted)

**RED Phase:**
- [ ] Create pressure scenarios (3+ combined pressures for discipline skills)
- [ ] Run scenarios WITHOUT skill — document baseline behavior verbatim
- [ ] Identify patterns in rationalizations/failures

**GREEN Phase:**
- [ ] Name: letters, numbers, hyphens only
- [ ] YAML frontmatter with `name` and `description` (max 1024 chars)
- [ ] Description: "Use when...", third person, specific triggers, no workflow summary
- [ ] Keywords throughout for search
- [ ] Clear overview with core principle
- [ ] Address specific baseline failures from RED
- [ ] Guidance form matches failure type
- [ ] Wording micro-tested (5+ reps, no-guidance control) for behavior-shaping skills
- [ ] One excellent example (not multi-language)
- [ ] Run scenarios WITH skill — verify compliance

**REFACTOR Phase:**
- [ ] Identify NEW rationalizations
- [ ] Add explicit counters (if discipline skill)
- [ ] Build rationalization table
- [ ] Create red flags list
- [ ] Re-test until bulletproof

**Quality Checks:**
- [ ] Flowchart only if decision non-obvious
- [ ] Quick reference table
- [ ] Common mistakes section
- [ ] No narrative storytelling
- [ ] Supporting files only for tools or heavy reference

## Hermes Agent Integration

Use Hermes Agent tools to verify and refine skills:

- **read_file** — read existing skills, reference files, and supporting documentation
- **search_files** — grep for keyword coverage across skills directories; verify naming and cross-references
- **write_file** — write new SKILL.md files and supporting reference files
- **patch** — make targeted edits to existing skills (prefer over write_file for edits)
- **delegate_task()** — dispatch subagents for pressure-scenario testing in fresh context, exactly like a one-shot API call: `delegate_task(prompt="...", context={"skill_under_test": "writing-skills", "pressure": "time"})`

**Token-efficiency check:** After writing, verify size with `read_file` or `search_files`. Target: getting-started workflows <150 words; frequently-loaded skills <200 words; other skills <500 words.

## The Bottom Line

**Creating skills IS TDD for process documentation.**

Same Iron Law: No skill without failing test first.
Same cycle: RED (baseline) → GREEN (write skill) → REFACTOR (close loopholes).
Same benefits: Better quality, fewer surprises, bulletproof results.

If you follow TDD for code, follow it for skills. It's the same discipline applied to documentation.