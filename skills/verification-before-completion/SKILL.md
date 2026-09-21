---
name: verification-before-completion
description: "Evidence before claims: run verification commands and confirm output before claiming work is complete, fixed, or passing."
version: 1.0.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [verification, evidence, testing, quality, completion, honesty]
    related_skills: [test-driven-development, requesting-code-review, systematic-debugging]
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags — STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

### Tests

```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

### Regression tests (TDD Red-Green)

```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

### Build

```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

### Deployments

```
✅ [Check HTTP status] [See: 200 OK] "Service is live"
❌ "Railway says deployed" (check the actual URL)
```

## Hermes Agent Integration

### Verification Commands by Project Type

**Python projects:**
```bash
# Tests
pytest tests/ -v --tb=short

# Linting
ruff check . || flake8 .

# Type checking
mypy . || pyright

# Build
pip install -e . && python -c "import package_name"
```

**Node/React projects:**
```bash
# Tests
npm test -- --coverage

# Linting
npm run lint

# Build
npm run build

# Type checking
npx tsc --noEmit
```

**Go projects:**
```bash
# Tests
go test ./... -v

# Build
go build ./...

# Vet
go vet ./...
```

### Using Terminal for Verification

Use the `terminal` tool to run verification commands. Read the FULL output:

```python
# Always check exit_code, not just output
result = terminal("pytest tests/ -v --tb=short")
if result["exit_code"] != 0:
    # Report actual failures, don't claim success
    print(result["output"])
```

### With requesting-code-review

This skill verifies your own work. The `requesting-code-review` skill adds an independent reviewer on top. They chain:

```
verification-before-completion (self-verify) → requesting-code-review (independent review) → commit
```

### With delegate_task

When a subagent reports "done", verify independently:

```python
# Don't trust the subagent's summary — check the actual state
result = terminal("git diff --stat")
# Confirm files actually changed
test_result = terminal("pytest tests/ -q")
# Confirm tests actually pass
```

## When "Done" Is Not Done

| State | Not Done Because |
|-------|-----------------|
| Code written | Tests not run |
| Tests written | Tests not passing |
| Tests passing | Not committed |
| Committed | Not pushed |
| Pushed | CI not green |
| CI green | Not merged |
| Merged | Not deployed |
| Deployed | Not verified at the URL |

"Done" means the end state the user asked for — not the step you just finished.