---
name: skill-creator
description: >-
  Create new skills, modify and improve existing skills, and measure skill performance.
  Use when users want to create a skill from scratch, edit, or optimize an existing skill,
  run evals to test a skill, benchmark skill performance with variance analysis, or optimize
  a skill's description for better triggering accuracy.
version: 1.0.0
author: "Hermes Agent (adapted from anthropics/skills)"
license: MIT
platforms:
  - linux
  - macos
  - windows
metadata:
  hermes:
    tags:
      - skill-creation
      - evaluation
      - benchmarking
      - optimization
      - testing
      - development
    related_skills:
      - hermes-agent
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

## Overview

1. Decide what the skill should do and roughly how
2. Write a draft of the skill
3. Create test prompts and run Hermes Agent (with the skill) on them
4. Evaluate results qualitatively and quantitatively
   - While runs happen, draft quantitative evals. Use `eval-viewer/generate_review.py` to show results.
5. Rewrite the skill based on feedback and benchmark flaws
6. Repeat until satisfied, then expand the test set

Figure out where the user is in this process and help them progress. Be flexible — if the user says "just vibe with me", do that. After the skill is done, run the description improver to optimize triggering.

---

## Creating a Skill

### Capture Intent

Start by understanding intent. The conversation might already contain a workflow to capture. Extract answers from history — tools used, steps, corrections, formats. The user fills gaps and confirms before proceeding.

1. What should this skill enable Hermes Agent to do?
2. When should this skill trigger? (user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases? Objectively verifiable outputs (file transforms, data extraction, code generation) benefit from test cases. Subjective outputs (writing, art) often don't. Suggest the default, let the user decide.

### Interview and Research

Proactively ask about edge cases, formats, example files, success criteria, dependencies. Research in parallel via subagents if available. Come prepared with context to reduce burden on the user.

### Write the SKILL.md

- **name**: Skill identifier (kebab-case)
- **description**: When to trigger, what it does. The primary triggering mechanism — include what the skill does AND specific contexts for when to use it. Make descriptions slightly "pushy" to combat undertriggering.
- **version**, **author**, **license**, **platforms**: Standard metadata
- **the body**: Markdown instructions

### Skill Anatomy

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

### Progressive Disclosure

1. **Metadata** (name + description) — Always in context (~100 words)
2. **SKILL.md body** — In context when skill triggers (<500 lines ideal)
3. **Bundled resources** — As needed (unlimited; scripts execute without loading)

Keep SKILL.md under 500 lines. Reference files clearly with guidance on when to read them. For large reference files (>300 lines), include a table of contents.

**Domain organization**: When a skill supports multiple domains, organize by variant in `references/`. Hermes Agent reads only the relevant reference file.

### Writing Style

Explain *why* things are important rather than heavy-handed MUSTs. Use theory of mind; make the skill general, not narrow. Write a draft, then review with fresh eyes and improve. Prefer the imperative form.

**Output format pattern:**
```markdown
## Report structure
Use this template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern:**
```markdown
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

Skills must not contain malware or content that compromises security. A skill's contents should not surprise the user in their intent.

### Test Cases

Come up with 2-3 realistic test prompts — what a real user would say. Share them: "Here are a few test cases. Do these look right, or add more?" Then run them.

Save to `evals/evals.json`. Don't write assertions yet — just prompts:

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

See `references/schemas.md` for the full schema (including `assertions`, added later).

---

## Running and Evaluating Test Cases

One continuous sequence — don't stop partway. Put results in `<skill-name>-workspace/` as a sibling to the skill. Organize by iteration (`iteration-1/`, `iteration-2/`), each test case gets a directory.

### Step 1: Spawn all runs (with-skill AND baseline) simultaneously

For each test case, spawn two subagents — one with the skill, one without. Launch everything at once.

**With-skill:** Run the task with the skill path, save outputs to `with_skill/outputs/`.
**Baseline:** For new skills, no skill (save to `without_skill/outputs/`). For improving existing skills, snapshot the old version first, point baseline at it (save to `old_skill/outputs/`).

Write `eval_metadata.json` per test case with a descriptive name:
```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

### Step 2: While runs are in progress, draft assertions

Draft quantitative assertions and explain them to the user. Good assertions are objectively verifiable with descriptive names. Subjective skills are better evaluated qualitatively. Update `eval_metadata.json` and `evals/evals.json`.

### Step 3: Capture timing data as runs complete

Save immediately to `timing.json` in each run directory:
```json
{"total_tokens": 84852, "duration_ms": 23332, "total_duration_seconds": 23.3}
```
Process each notification as it arrives — this data isn't persisted elsewhere.

### Step 4: Grade, aggregate, and launch the viewer

1. **Grade** — spawn a grader subagent reading `agents/grader.md`. Save to `grading.json`. Expectations must use fields `text`, `passed`, `evidence` (the viewer depends on these). For programmable checks, write and run a script.

2. **Aggregate** — run:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   Produces `benchmark.json` and `benchmark.md` with pass_rate, time, tokens (mean ± stddev and delta).

3. **Analyst pass** — surface patterns the aggregate stats hide. See `agents/analyzer.md`: non-discriminating assertions, high-variance evals, time/token tradeoffs.

4. **Launch the viewer:**
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json > /dev/null 2>&1 &
   ```
   For iteration 2+, add `--previous-workspace <workspace>/iteration-<N-1>`. In headless environments, use `--static <output_path>`. Use `generate_review.py`, not custom HTML.

5. **Tell the user:** "I've opened the results — 'Outputs' for test case review, 'Benchmark' for quantitative comparison. Let me know when done."

### Step 5: Read the feedback

Read `feedback.json`. Empty feedback means it was fine. Focus improvements on test cases with specific complaints. Kill the viewer when done.

---

## Improving the Skill

### How to think about improvements

1. **Generalize from feedback.** We're creating skills usable a million times across many prompts. Don't overfit to the few test examples. Try different metaphors or patterns rather than fiddly changes.

2. **Keep the prompt lean.** Remove things not pulling their weight. Read transcripts — if the skill makes the model waste time, cut those parts.

3. **Explain the why.** LLMs are smart. If you're writing ALWAYS/NEVER in caps, that's a yellow flag — reframe and explain the reasoning.

4. **Look for repeated work.** If all test cases resulted in writing similar helper scripts, bundle that script in `scripts/` and tell the skill to use it.

Write a draft revision, review with fresh eyes, improve. Get into the head of the user.

### The iteration loop

1. Apply improvements
2. Rerun all test cases into `iteration-<N+1>/`, including baselines
3. Launch reviewer with `--previous-workspace` pointing at the previous iteration
4. Wait for user review
5. Read feedback, improve, repeat

Keep going until: the user is happy, feedback is all empty, or you're not making meaningful progress.

---

## Advanced: Blind Comparison

For rigorous comparison between skill versions, read `agents/comparator.md` and `agents/analyzer.md`. Give two outputs to an independent agent without labels, let it judge, then analyze why the winner won. Optional, requires subagents.

---

## Description Optimization

The `description` field determines whether Hermes Agent invokes a skill. After creating or improving a skill, offer to optimize it.

### Step 1: Generate trigger eval queries

Create 20 queries — should-trigger and should-not-trigger. Save as JSON:
```json
[{"query": "the user prompt", "should_trigger": true}]
```

Queries must be realistic — concrete, specific, with detail (file paths, context, column names). Focus on edge cases. For should-not-trigger, use near-misses sharing keywords but needing something different.

### Step 2: Review with user

Bad eval queries lead to bad descriptions. Present the set for user review.

### Step 3: Run the optimization loop

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 --verbose
```

This handles the full loop: 60% train / 40% held-out test split, evaluates (3 runs per query), proposes improvements, re-evaluates, iterates up to 5 times. Returns JSON with `best_description` selected by test score to avoid overfitting.

### Step 4: Apply the result

Update the skill's SKILL.md frontmatter with `best_description`. Show before/after and report scores.

---

## Packaging

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

Validates and creates a `.skill` file (zip archive). When updating an existing skill, preserve the original name and copy to a writeable location before editing.

---

## Reference Files

- `agents/grader.md` — Evaluate assertions against outputs
- `agents/comparator.md` — Blind A/B comparison
- `agents/analyzer.md` — Analyze why one version beat another
- `references/schemas.md` — JSON structures for evals.json, grading.json, benchmark.json, etc.

---

## Core Loop

1. Figure out what the skill is about
2. Draft or edit the skill
3. Run Hermes Agent (with the skill) on test prompts
4. With the user, evaluate outputs: create benchmark.json, run `eval-viewer/generate_review.py`, run quantitative evals
5. Repeat until satisfied
6. Package the final skill