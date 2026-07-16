---
name: skill-creator-plus
description: Create, test, evaluate, and iteratively improve Claude skills. Use when users say "create a skill", "make a skill for", "write a SKILL.md", "turn this into a skill", "run evals", "test my skill", "benchmark my skill", "optimize my skill description", "improve triggering", "blind comparison", "A/B test my skill", or want to package a skill for distribution. Also triggers on "skill-creator", editing an existing skill, or reviewing skill quality.
license: MIT
metadata:
  author: Yaniv Golan
  version: "0.6.0"
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

At a high level, the process of creating a skill goes like this:

- Decide what you want the skill to do and roughly how it should do it
- Write a draft of the skill
- Create a few test prompts and run claude-with-access-to-the-skill on them
- Help the user evaluate the results both qualitatively and quantitatively
  - While the runs happen in the background, draft some quantitative evals if there aren't any (if there are some, you can either use as is or modify if you feel something needs to change about them). Then explain them to the user (or if they already existed, explain the ones that already exist)
  - Use the `eval-viewer/generate_review.py` script to show the user the results for them to look at, and also let them look at the quantitative metrics
- Rewrite the skill based on feedback from the user's evaluation of the results (and also if there are any glaring flaws that become apparent from the quantitative benchmarks)
- Repeat until you're satisfied
- Expand the test set and try again at larger scale

Your job when using this skill is to figure out where the user is in this process and then jump in and help them progress through these stages. So for instance, maybe they're like "I want to make a skill for X". You can help narrow down what they mean, write a draft, write the test cases, figure out how they want to evaluate, run all the prompts, and repeat.

On the other hand, maybe they already have a draft of the skill. In this case you can go straight to the eval/iterate part of the loop.

Of course, you should always be flexible and if the user is like "I don't need to run a bunch of evaluations, just vibe with me", you can do that instead.

Then after the skill is done (but again, the order is flexible), you can also run the skill description improver, which we have a whole separate script for, to optimize the triggering of the skill.

Cool? Cool.

## Communicating with the user

The skill creator is liable to be used by people across a wide range of familiarity with coding jargon. If you haven't heard (and how could you, it's only very recently that it started), there's a trend now where the power of Claude is inspiring plumbers to open up their terminals, parents and grandparents to google "how to install npm". On the other hand, the bulk of users are probably fairly computer-literate.

So please pay attention to context cues to understand how to phrase your communication! In the default case, just to give you some idea:

- "evaluation" and "benchmark" are borderline, but OK
- for "JSON" and "assertion" you want to see serious cues from the user that they know what those things are before using them without explaining them

It's OK to briefly explain terms if you're in doubt, and feel free to clarify terms with a short definition if you're unsure if the user will get it.

---

## Creating a skill

### Capture Intent

Start by understanding the user's intent. The current conversation might already contain a workflow the user wants to capture (e.g., they say "turn this into a skill"). If so, extract answers from the conversation history first — the tools used, the sequence of steps, corrections the user made, input/output formats observed. The user may need to fill the gaps, and should confirm before proceeding to the next step.

1. What should this skill enable Claude to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. **Which use case category does this fall into?** (see `references/official-guide-patterns.md` for details)
   - **Document & Asset Creation** — consistent, high-quality output (docs, presentations, code, designs)
   - **Workflow Automation** — multi-step processes benefiting from consistent methodology
   - **MCP Enhancement** — workflow guidance layered on top of MCP tool access
   For a more granular taxonomy (9 types from Anthropic's internal experience), see the "Expanded Skill Type Taxonomy" section of the reference file — it covers Library & API Reference, Product Verification, Data Fetching & Analysis, Business Process & Team Automation, Code Scaffolding & Templates, Code Quality & Review, CI/CD & Deployment, Runbooks, and Infrastructure Operations. Knowing the type helps choose the right techniques.
5. Should we set up test cases to verify the skill works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Skills with subjective outputs (writing style, art) often don't need them. Suggest the appropriate default based on the skill type, but let the user decide.

### Define Success Criteria

Before writing anything, help the user articulate what "working" looks like. These are aspirational targets, not precise thresholds — but they keep the iteration loop focused.

- **Quantitative**: Does the skill trigger on ~90% of relevant queries? Does it complete the workflow in fewer tool calls than without? Are there zero failed API calls?
- **Qualitative**: Can a user get through the workflow without needing to redirect Claude? Are results consistent across sessions? Does a new user succeed on their first try?

See `references/official-guide-patterns.md` (Success Criteria section) for measurement approaches.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available MCPs - if useful for research (searching docs, finding similar skills, looking up best practices), research in parallel via subagents if available, otherwise inline. Come prepared with context to reduce burden on the user.

### Write the SKILL.md

Based on the user interview, fill in these components:

**Portable fields (work on every agentskills.io host — Claude, Gemini CLI, Cursor, OpenCode, etc.):**

- **name**: Skill identifier (kebab-case only, no spaces or capitals, must match the folder name)
- **description**: The single most important field. It's how agents decide whether to load the skill. Write it as a **trigger, not a summary**: `[What it does] + [When to use it] + [Key capabilities]`. Must be under 1024 characters, no XML tags. Make it assertive — models tend to undertrigger. On portable hosts this is the only discovery text the model sees, so it must stand alone. See `references/official-guide-patterns.md` (Description Field Formula) for the full formula and examples.
- **license** (optional): License name or bundled license file reference.
- **compatibility** (optional, max 500 chars): Use when your skill has environment requirements (e.g. "Requires git, docker"; "Designed for Claude Code").
- **metadata** (optional): Arbitrary key-value pairs. Recommended: `author`, `version`.
- **allowed-tools** (optional, experimental): Space-separated pre-approved tool patterns.

**Claude-specific extensions (supported; skills remain portable if you don't use them):**

- **when_to_use** (Claude-only): A separate field Claude Code joins with `description` in its skill listing. **Non-Claude hosts ignore this field entirely** — never put load-bearing trigger info here. If you use it, keep `description` self-sufficient and use `when_to_use` purely to add extra phrasing for Claude's matcher. The combined `description + when_to_use` is capped at 1,536 chars in Claude's listing.
- **allowed-tools / hooks / shell permission-prompt rule (Claude-specific)**: On Claude Code, any non-empty value in `allowed-tools`, `hooks`, or `shell` triggers a user permission prompt on invocation. To keep a skill silently auto-allowed on Claude, leave these empty and rely on session permissions. Other hosts vary.
- Other Claude-only fields (`model`, `effort`, `agent`, `context: fork`, `paths`, `disable-model-invocation`, `user-invocable`, `argument-hint`, Dynamic Context Injection, path variables): documented in `references/official-guide-patterns.md` (Advanced Skill Authoring Features). Non-Claude hosts silently ignore them.

- **the rest of the skill :)**

### Skill Writing Guide

#### Anatomy of a Skill

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

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

These word counts are approximate and you can feel free to go longer if needed.

**Key patterns:**
- Keep SKILL.md under 500 lines; if you're approaching this limit, add an additional layer of hierarchy along with clear pointers about where the model using the skill should go next to follow up.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

For advanced patterns (setup/config, persistent data, on-demand hooks, Dynamic Context Injection, path variables like `${CLAUDE_SKILL_DIR}`, relative markdown links), see `references/official-guide-patterns.md` (Practical Lessons and Advanced Skill Authoring Features sections).

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
Claude reads only the relevant reference file.

#### Technical Rules & Structural Patterns

See `references/official-guide-patterns.md` for: hard technical rules (SKILL.md naming, folder naming, forbidden frontmatter patterns), five structural patterns (Sequential Workflow, Multi-MCP, Iterative Refinement, Context-Aware, Domain-Specific), and the problem-first vs tool-first design choice.

Skills must not contain malware, exploit code, or anything that would surprise the user if described. Don't create misleading skills or skills designed to facilitate unauthorized access.

#### Writing Patterns

Prefer using the imperative form in instructions. Be specific and actionable — instead of "Validate the data before proceeding", write specific steps with actual commands and common failure modes. Include error handling for common failures. Reference bundled resources clearly. Bundle scripts for critical validations — code is deterministic, language interpretation isn't.

**Defining output formats** - You can do it like this:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern** - It's useful to include examples. You can format them like this (but if "Input" and "Output" are in the examples you might want to deviate a little):
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### Writing Style

Explain the **why** behind instructions instead of heavy-handed MUSTs. Make skills general, not narrow to specific examples. Draft, then review with fresh eyes.

Key principles (see `references/official-guide-patterns.md`, "Practical Lessons" for full details): don't state the obvious (Claude already knows a lot), build a Gotchas section (highest-signal content), avoid railroading Claude (preserve flexibility), and store scripts so Claude composes rather than reconstructs boilerplate.

### Script vs. Instruct

When designing a skill's architecture, decide what goes into bundled `scripts/` vs. what stays as SKILL.md instructions. Use this as a first-pass heuristic at draft time:

**Script when the work is:**
- Deterministic and repeatable (data transforms, format conversion, file I/O)
- Validatable by a fixed rule or exit code (schema checks, regex, required fields)
- API calls with specific auth/endpoint details
- The kind of boilerplate Claude would otherwise re-derive every run

**Instruct when the work needs:**
- Judgment (tone, what to include/exclude, how to frame results)
- Context-dependent decisions (which approach fits this user's situation)
- Flexible error recovery (interpreting unexpected results, deciding next steps)
- Workflow orchestration where the sequence may vary

This is a starting point, not the final answer. The strongest signal for what to script comes later, from observing convergence across eval runs (see "Look for repeated work across test cases" below) — if 2-3 independent runs all reinvent the same helper, that's empirical evidence the logic belongs in a script. Don't over-script upfront; let the convergence signal guide you. See [Script vs. Instruct decision framework](references/official-guide-patterns.md) ("When to Script vs. When to Instruct") for the full framework and examples.

**When you do bundle a script, design it for agent consumption** — non-interactive, `--help`-documented, structured output (JSON/CSV), helpful errors, meaningful exit codes, idempotent by default. A script that works fine for a human can be unusable for an agent. See [official-guide-patterns.md](references/official-guide-patterns.md) ("Designing Scripts for Agent Use") for the full conventions.

### Test Cases

**Pro Tip from the official guide: Iterate on a single task before expanding.** The most effective skill creators iterate on a single challenging task until Claude succeeds, then extract the winning approach into a skill. This leverages in-context learning and provides faster signal than broad testing. Once you have a working foundation, expand to multiple test cases for coverage.

After writing the skill draft, come up with 2-3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: [you don't have to use this exact language] "Here are a few test cases I'd like to try. Do these look right, or do you want to add more?" Then run them.

Per the official guide, effective testing covers three areas:
1. **Triggering tests** — Does the skill load at the right times? (obvious tasks, paraphrased requests, and confirming it doesn't trigger on unrelated topics)
2. **Functional tests** — Does the skill produce correct outputs? (valid outputs, API calls succeed, error handling works, edge cases covered)
3. **Performance comparison** — Does the skill actually improve results vs. baseline? (fewer tool calls, fewer user corrections, lower token usage)

Save test cases to `evals.json` in a **committed sibling** of the skill directory — `<skill-name>-evals/evals.json` — never inside the skill directory itself. The definitions are the durable regression suite (commit them; run in CI if the skill has a repo); an eval file *inside* the skill dir would ship its own answer key to every install. See [Where evals live](references/schemas.md#where-evals-live) for the full layout. Don't write assertions yet — just the prompts. You'll draft assertions in the next step while the runs are in progress.

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

See `references/schemas.md` for the full schema (including the `assertions` field, which you'll add later — note: in the *output* file grading.json the graded entries are called `expectations`; the schemas reference documents both).

## Running and evaluating test cases

This section is one continuous sequence — don't stop partway through. Do NOT use `/skill-test` or any other testing skill.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory. Within the workspace, organize results by iteration (`iteration-1/`, `iteration-2/`, etc.) and within that, each test case gets a directory named for what it tests (e.g. `pdf-extraction/`, `multi-page-form/` — Step 1 explains the naming). Don't create all of this upfront — just create directories as you go.

### Step 1: Spawn all runs (with-skill AND baseline) in the same turn

For each test case, spawn two subagents in the same turn — one with the skill, one without. This is important: don't spawn the with-skill runs first and then come back for baselines later. Launch everything at once so it all finishes around the same time.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
- Also write outputs/user_notes.md: anything you were unsure about, workarounds you used, or things a human should review (write "none" if nothing)
- Also write outputs/metrics.json: {"total_tool_calls": <n>, "errors_encountered": <n>} — your best count of tool calls made and errors hit
```

**Baseline run** (same prompt, but the baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, save to `without_skill/outputs/`, with the same user_notes.md and metrics.json instructions.
- **Improving an existing skill**: the old version. Before editing, snapshot the skill (`cp -r <skill-path> <workspace>/skill-snapshot/`), then point the baseline subagent at the snapshot. Save to `old_skill/outputs/`.

Write an `eval_metadata.json` for each test case (assertions can be empty for now). Give each eval a descriptive name based on what it's testing — not just "eval-0". Use this name for the directory too. If this iteration uses new or modified eval prompts, create these files for each new eval directory — don't assume they carry over from previous iterations.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

### Step 2: While runs are in progress, draft assertions

Don't just wait for the runs to finish — you can use this time productively. Draft quantitative assertions for each test case and explain them to the user. If assertions already exist in `evals.json`, review them and explain what they check.

Good assertions are objectively verifiable and have descriptive names — they should read clearly in the benchmark viewer so someone glancing at the results immediately understands what each one checks. Subjective skills (writing style, design quality) are better evaluated qualitatively — don't force assertions onto things that need human judgment.

Update the `eval_metadata.json` files and `<skill-name>-evals/evals.json` with the assertions once drafted. Also explain to the user what they'll see in the viewer — both the qualitative outputs and the quantitative benchmark.

### Step 3: As runs complete, capture timing data

When each subagent task completes, you receive a notification containing `total_tokens` and `duration_ms`. Save this data immediately to `timing.json` in the run directory:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

This is the only opportunity to capture this data — it comes through the task notification and isn't persisted elsewhere. Process each notification as it arrives rather than trying to batch them.

### Step 4: Grade, aggregate, and launch the viewer

Once all runs are done:

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json` in each config directory (e.g., `eval-1/with_skill/grading.json`). The grading.json expectations array must use the fields `text`, `passed`, and `evidence` (not `name`/`met`/`details` or other variants) — the viewer depends on these exact field names. For assertions that can be checked programmatically, write and run a script rather than eyeballing it — scripts are faster, more reliable, and can be reused across iterations. If a check is also something a user of the finished skill would benefit from running themselves (e.g., a `validate_X.py` or `smoke_test_X.sh`), bundle it in the skill's `scripts/` directory so the same code serves both the eval grader and end users.

2. **Aggregate into benchmark** — run the aggregation script from the skill-creator directory:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   This produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens for each configuration, with mean ± stddev and the delta. If generating benchmark.json manually, see `references/schemas.md` for the exact schema the viewer expects, and order each with_skill run before its baseline counterpart in the `runs` array.

3. **Do an analyst pass** — read the benchmark data and surface patterns the aggregate stats might hide. See `agents/analyzer.md` (the "Analyzing Benchmark Results" section) for what to look for — things like assertions that always pass regardless of skill (non-discriminating), high-variance evals (possibly flaky), and time/token tradeoffs. Save the notes to `<workspace>/iteration-N/notes.json`, then merge them into the benchmark: `python -m scripts.aggregate_benchmark <workspace>/iteration-N --notes <workspace>/iteration-N/notes.json` — otherwise the viewer's "Analysis Notes" section stays empty.

4. **Launch the viewer** with both qualitative outputs and quantitative data:
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```
   For iteration 2+, also pass `--previous-workspace <workspace>/iteration-<N-1>`.

   **Cowork / headless environments:** If `webbrowser.open()` is not available or the environment has no display, use `--static <output_path>` to write a standalone HTML file instead of starting a server. When the user clicks "Submit All Reviews", the viewer displays the raw JSON in a copyable textarea (no file is downloaded — blob downloads blank the page in embedded viewers). The user pastes the JSON directly into the chat, or saves it themselves into the workspace as `feedback.json`. **Important: In static mode, you cannot read feedback.json from disk** — see `references/environments.md` (Cowork section) for how to handle the feedback loop.

Note: please use generate_review.py to create the viewer; there's no need to write custom HTML.

5. **Tell the user** something like: "I've opened the results in your browser. There are two tabs — 'Outputs' lets you click through each test case and leave feedback, 'Benchmark' shows the quantitative comparison. When you're done, come back here and let me know."

### What the user sees in the viewer

The "Outputs" tab shows one test case at a time:
- **Prompt**: the task that was given
- **Output**: the files the skill produced, rendered inline where possible
- **Previous Output** (iteration 2+): collapsed section showing last iteration's output
- **Formal Grades** (if grading was run): collapsed section showing assertion pass/fail
- **Feedback**: a textbox that auto-saves as they type
- **Previous Feedback** (iteration 2+): their comments from last time, shown below the textbox

The "Benchmark" tab shows the stats summary: pass rates, timing, and token usage for each configuration, with per-eval breakdowns and analyst observations.

Navigation is via prev/next buttons or arrow keys. When done, they click "Submit All Reviews" which saves all feedback to `feedback.json`.

### Step 5: Read the feedback

When the user tells you they're done, read `feedback.json`:

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "the chart is missing axis labels", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."},
    {"run_id": "eval-2-with_skill", "feedback": "perfect, love this", "timestamp": "..."}
  ],
  "status": "complete"
}
```

Empty feedback means the user thought it was fine. Focus your improvements on the test cases where the user had specific complaints.

Kill the viewer server when you're done with it:

```bash
kill $VIEWER_PID 2>/dev/null
```

---

## Improving the skill

This is the heart of the loop. You've run the test cases, the user has reviewed the results, and now you need to make the skill better based on their feedback.

### How to think about improvements

1. **Generalize from the feedback.** The big picture thing that's happening here is that we're trying to create skills that can be used a million times (maybe literally, maybe even more who knows) across many different prompts. Here you and the user are iterating on only a few examples over and over again because it helps move faster. The user knows these examples in and out and it's quick for them to assess new outputs. But if the skill you and the user are codeveloping works only for those examples, it's useless. Rather than put in fiddly overfitty changes, or oppressively constrictive MUSTs, if there's some stubborn issue, you might try branching out and using different metaphors, or recommending different patterns of working. It's relatively cheap to try and maybe you'll land on something great.

2. **Keep the prompt lean.** Remove things that aren't pulling their weight. Make sure to read the transcripts, not just the final outputs — if it looks like the skill is making the model waste a bunch of time doing things that are unproductive, you can try getting rid of the parts of the skill that are making it do that and seeing what happens.

3. **Explain the why.** Try hard to explain the **why** behind everything you're asking the model to do. Today's LLMs are *smart*. They have good theory of mind and when given a good harness can go beyond rote instructions and really make things happen. Even if the feedback from the user is terse or frustrated, try to actually understand the task and why the user is writing what they wrote, and what they actually wrote, and then transmit this understanding into the instructions. If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag — if possible, reframe and explain the reasoning so that the model understands why the thing you're asking for is important. That's a more humane, powerful, and effective approach.

4. **Look for repeated work across test cases.** Read the transcripts from the test runs and notice if the subagents all independently wrote similar helper scripts or took the same multi-step approach to something. If all 3 test cases resulted in the subagent writing a `create_docx.py` or a `build_chart.py`, that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and tell the skill to use it. This saves every future invocation from reinventing the wheel. This works in both directions: scripts you bundle for end users (validators, smoke tests) can also be reused as eval-time grader assertions in later iterations. See [Script vs. Instruct decision framework](references/official-guide-patterns.md) ("When to Script vs. When to Instruct") for guidance on what belongs in a script vs. what should stay as instructions.

5. **Check against the official troubleshooting patterns.** Consult `references/official-guide-patterns.md` (Troubleshooting Guide section) for common issues: instructions not followed (too verbose? buried? ambiguous?), skill not triggering (description too generic?), skill over-triggering (needs negative triggers or scope clarification?), large context degradation (SKILL.md too big? move content to references/).

This task is pretty important (we are trying to create billions a year in economic value here!) and your thinking time is not the blocker; take your time and really mull things over. I'd suggest writing a draft revision and then looking at it anew and making improvements. Really do your best to get into the head of the user and understand what they want and need.

### The iteration loop

After improving the skill:

1. Apply your improvements to the skill
2. Rerun all test cases into a new `iteration-<N+1>/` directory, including baseline runs. If you're creating a new skill, the baseline is always `without_skill` (no skill) — that stays the same across iterations. If you're improving an existing skill, use your judgment on what makes sense as the baseline: the original version the user came in with, or the previous iteration.
3. Launch the reviewer with `--previous-workspace` pointing at the previous iteration
4. Wait for the user to review and tell you they're done
5. Read the new feedback, improve again, repeat

Keep going until:
- The user says they're happy
- The feedback is all empty (everything looks good)
- You're not making meaningful progress

Remember: Anthropic's own experience is that most of their best skills **began as just a few lines and a single gotcha**, then got better over time as Claude hit new edge cases. It's fine to ship something small and iterate — perfection on day one is not the goal.

---

## Advanced: Blind comparison

For situations where you want a more rigorous comparison between two versions of a skill (e.g., the user asks "is the new version actually better?"), there's a blind comparison system. Read `agents/comparator.md` and `agents/analyzer.md` for the details. The basic idea is: give two outputs to an independent agent without telling it which is which, and let it judge quality. Then analyze why the winner won. When you run more than one comparison round, alternate which version is labeled A and which is B between rounds, and record the mapping (e.g. `comparison_mapping.json` next to each comparator output) so results can be unblinded later — judges drift toward the first-presented output, and counterbalancing cancels that bias.

This is optional, requires subagents, and most users won't need it. The human review loop is usually sufficient.

---

## Description Optimization

The description field is the primary mechanism that determines whether Claude invokes a skill. After creating or improving a skill, offer to optimize it: generate ~20 realistic trigger eval queries, have the user review them, then run the automated optimization loop (`scripts/run_loop.py` — real `claude -p` calls, run from the skill-creator-plus skill directory) and apply the resulting `best_description`.

Read `references/description-optimization.md` for the full procedure before starting — it covers how to write good eval queries, the user-review HTML template, the exact run_loop command and flags, and how triggering works under the hood. Requires the `claude` CLI (Claude Code / Cowork only).

---

### Validate Against the Official Checklist

Before packaging, run through the quick checklist from `references/official-guide-patterns.md` to catch common issues:

- [ ] Folder named in kebab-case
- [ ] SKILL.md file exists (exact spelling, case-sensitive)
- [ ] YAML frontmatter has `---` delimiters
- [ ] name field: kebab-case, no spaces, no capitals, matches folder name
- [ ] description includes WHAT the skill does and WHEN to use it
- [ ] No XML tags (< >) anywhere in frontmatter
- [ ] No "claude" or "anthropic" in the skill name
- [ ] Instructions are clear and actionable (not vague)
- [ ] Error handling included for likely failure modes
- [ ] Examples provided where helpful
- [ ] References clearly linked from SKILL.md
- [ ] SKILL.md stays under ~500 lines (detailed content in references/)
- [ ] No README.md inside the skill folder

You can run `python -m scripts.quick_validate <path-to-skill>` to check some of these automatically.

Also run `python -m scripts.check_portability <path-to-skill> --target <claude-code|claude-ai|cowork|all>` — a stdlib-only cross-runtime linter (no dependencies, runs in any environment). It flags constructs that break on the skill's target runtime: an over-cap `description`, subagent use (absent on Claude.ai), `claude` CLI use (absent on Claude.ai), browser/server assumptions (no display in Cowork/Claude.ai), and third-party Python imports in bundled scripts (Cowork's sandbox lacks them and can't `pip install`). Pass `--target` matching where the skill will run; `--strict` to gate.

If `cowork-harness` is installed, also run its two token-free static checks — `cowork-harness lint-skill --strict <skill-dir>` and `cowork-harness analyze-skill --strict <skill-dir>`. They're cheap and safe on any skill, and catch runtime bugs the checklist can't (host-path leaks, interactive-artifact write-backs lost under Cowork); their findings matter most for **Cowork-targeted** skills. Optional — skip silently if the tool isn't installed. See `references/environments.md` § *Testing Cowork-targeted skills with cowork-harness*.

### Package the Skill

Package the final skill into a distributable `.skill` file (run from the skill-creator-plus skill directory):

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

Tell the user the path of the resulting `.skill` file so they can install or share it. If the `present_files` tool happens to be available (Claude.ai), additionally present the `.skill` file directly — but packaging itself works everywhere Python does, so never skip it just because that tool is missing.

---

## Environment-specific instructions

The core workflow above assumes Claude Code with subagents. On **Claude.ai** (no subagents, no `claude` CLI) and in **Cowork** (no browser/display; static viewer + paste-back feedback loop), several mechanics change. Before running test cases, the viewer, or packaging in those environments, read `references/environments.md`.

---

## Reference files

The agents/ directory contains instructions for specialized subagents. Read them when you need to spawn the relevant subagent.

- `agents/grader.md` — How to evaluate assertions against outputs
- `agents/comparator.md` — How to do blind A/B comparison between two outputs
- `agents/analyzer.md` — How to analyze why one version beat another

The references/ directory has additional documentation:
- `references/schemas.md` — JSON structures for evals.json, grading.json, etc.
- `references/official-guide-patterns.md` — Anthropic's official best practices: use case categories, description formula, five skill patterns, instructions best practices, technical rules, troubleshooting guide, and quick checklist. **Consult this when designing a new skill or diagnosing issues with an existing one.**
- `references/environments.md` — Claude.ai and Cowork adaptations (read when not in Claude Code)
- `references/description-optimization.md` — full triggering-optimization procedure

---

Repeating one more time the core loop here for emphasis:

- Figure out what the skill is about
- Draft or edit the skill
- Run claude-with-access-to-the-skill on test prompts
- With the user, evaluate the outputs:
  - Create benchmark.json and run `eval-viewer/generate_review.py` to help the user review them
  - Run quantitative evals
- Repeat until you and the user are satisfied
- Package the final skill and return it to the user.

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you're in Cowork, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.

Good luck!
