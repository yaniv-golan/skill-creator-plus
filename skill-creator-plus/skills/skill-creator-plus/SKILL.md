---
name: skill-creator-plus
description: Create, test, evaluate, and improve Claude skills — and answer questions about how skills work. Use for "create a skill", "make a skill for", "write a SKILL.md", "turn this into a skill", "run evals", "test/benchmark my skill", "optimize my skill description", "improve triggering", "A/B test my skill", "blind comparison", packaging for distribution, editing an existing skill, or reviewing skill quality. Also for a single narrow question about skill mechanics, however small — referencing a bundled script or reference doc, path variables, frontmatter fields, directory layout, size limits, or what breaks across Claude Code, Claude.ai and Cowork.
license: MIT
metadata:
  author: Yaniv Golan
  version: "0.14.0"
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

At a high level, the process of creating a skill goes like this:

- Decide what you want the skill to do and roughly how it should do it
- Write a draft of the skill
- Create a few test prompts and run claude-with-access-to-the-skill on them
- Help the user evaluate the results both qualitatively and quantitatively
  - While the runs happen, draft quantitative evals if there aren't any (or adapt the existing ones), then explain them to the user (or if they already existed, explain the ones that already exist)
  - Use the `eval-viewer/generate_review.py` script to show the user the results for them to look at, and also let them look at the quantitative metrics
- Rewrite the skill based on feedback from the user's evaluation of the results (and also if there are any glaring flaws that become apparent from the quantitative benchmarks)
- Repeat until you're satisfied
- Expand the test set and try again at larger scale

Figure out where the user is in this loop and join them there. "I want a skill for X" starts at the top; an existing draft jumps straight to eval/iterate. Order is flexible, and once the skill is done you can run the description improver (a separate script) to sharpen its triggering.

**If a section this file refers to seems to be missing, it was truncated — re-read `SKILL.md` from disk before continuing.** Compaction cuts the tail and writes the cut back, so what's in context can be a partial copy. (This works only when a truncation marker is present; it cannot detect a skill dropped whole by the combined cap.)

### The one-pass path

Often the user wants a working skill now, not an eval report. That is a legitimate route, not a shortcut — take it when they ask for the skill itself, or say they don't want evals:

1. **Draft** the skill (Capture Intent → Write the SKILL.md, below).
2. **Smoke-test every script you bundled**, directly: run it on synthetic input with the problems planted (malformed rows, wrong delimiter, unusual encoding, empty and header-only files, a missing file), plus one realistic case. A script that only ever ran on clean input is untested. When a smoke test fails, work out whether the script or the *test* is wrong before changing either — a synthetic fixture is a guess too. A check worth keeping belongs in the skill's own `scripts/`, so its users can run it as well.
3. **Validate**: `quick_validate` then `check_portability` (see *Validate Against the Official Checklist*, which says how to find them; never hand-roll the package).
4. **Package and deliver** it (see *Package the Skill*).
5. **Then offer** the eval loop and description optimization as follow-ups.

Steps 2 and 3 *are* the verification when you skip evals — shipping without eval evidence is fine, shipping with nothing exercised is not. **No sub-agent tool, or instructions saying where to work or how files reach the user? Read `references/environments.md` first** — paths and delivery differ per runtime.

## Communicating with the user

Users span a wide range of familiarity with coding jargon — from people who just opened a terminal for the first time to seasoned engineers. Calibrate to the person, not to the median.

Read the context cues and pitch accordingly. In the default case:

- "evaluation" and "benchmark" are borderline, but OK
- for "JSON" and "assertion" you want to see serious cues from the user that they know what those things are before using them without explaining them

If you're unsure a term will land, define it briefly in passing.

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
   For a finer taxonomy (9 types, from library/API reference through runbooks and infra ops), see "Expanded Skill Type Taxonomy" in the reference file. Knowing the type helps choose the right techniques.
5. Should we set up test cases to verify the skill works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Skills with subjective outputs (writing style, art) often don't need them. Suggest the appropriate default based on the skill type, but let the user decide.

### Define Success Criteria

Before writing anything, help the user articulate what "working" looks like. These are aspirational targets, not precise thresholds — but they keep the iteration loop focused.

Cover both **quantitative** (does it trigger reliably? fewer tool calls than without? no failed calls?) and **qualitative** (can the user finish without redirecting Claude? consistent across sessions?). See `references/official-guide-patterns.md` (Success Criteria) for the full set and how to measure them.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available MCPs - if useful for research (searching docs, finding similar skills, looking up best practices), research in parallel via subagents if available, otherwise inline. Come prepared with context to reduce burden on the user.

### Write the SKILL.md

**Where the skill directory goes:** somewhere the user can keep it — a location in their project, confirmed with them if unclear. Never inside this plugin's own directory (read-only on a plugin install), and never a scratch directory. **Build it in one place and never keep a second copy to sync.** Authoring is mostly shell work, and the shell's cwd is not the file tools' — so name the destination once and address it per family: in Cowork, build in the directory your instructions designate for your work (outputs if named, else your working directory), by absolute path, each family in its own spelling. `references/environments.md` has the mechanism.

Based on the user interview, fill in these components:

**Portable fields (work on every agentskills.io host — Claude, Gemini CLI, Cursor, OpenCode, etc.):**

- **name**: Skill identifier (kebab-case only, no spaces or capitals, must match the folder name)
- **description**: The single most important field. It's how agents decide whether to load the skill. Write it as a **trigger, not a summary**: `[What it does] + [When to use it] + [Key capabilities]`. Must be under 1024 characters, no XML tags. Make it assertive — models tend to undertrigger. On portable hosts this is the only discovery text the model sees, so it must stand alone. See `references/official-guide-patterns.md` (Description Field Formula) for the full formula and examples.
- **license** (optional): License name or bundled license file reference.
- **compatibility** (optional, max 500 chars): Use when your skill has environment requirements (e.g. "Requires git, docker"; "Designed for Claude Code").
- **metadata** (optional): Arbitrary key-value pairs. Recommended: `author`, `version`.
- **When the user hasn't specified**: omit `license` and `metadata.author` rather than inventing them — a licence or byline you made up is a claim on their behalf. Default `metadata.version` to `0.1.0`.
- **allowed-tools** (optional, experimental): Space-separated pre-approved tool patterns.

**Claude-specific extensions (supported; skills remain portable if you don't use them):**

- **when_to_use** (Claude-only): extra phrasing for Claude's matcher. **Never put load-bearing trigger info here** — non-Claude hosts ignore it, and under Cowork it is only half-visible even on Claude. Keep `description` self-sufficient.
- **allowed-tools / disallowed-tools / shell (Claude-specific)**: these *grant and restrict*; none of them triggers a permission prompt. The real gate is **workspace trust**, accepted once per folder — so review a project's skills before trusting its repo.
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

**Reaching a bundled script:** the skill-directory variable (`CLAUDE_SKILL_DIR`, braced) is a load-time
substitution into `SKILL.md` text only — it arrives literally in a `references/*.md` and is the empty
string in a shell. There is no skill-relative path resolution; CWD is never the skill directory.
**Don't hand-write the stanza** — paste it from `assets/skill-script-invocation.md`, which carries the
exact token form (a SKILL.md cannot show it: the runtime substitutes it at load). Under Cowork,
where the shell and file tools are different mounts, use its stanza B (find from the shell's side) —
not a `bin/` launcher: none has been seen on Cowork's shell PATH, and a top-level `bin/` makes a plugin
unpublishable through claude.ai organization settings (`claude plugin validate` does not warn).
`assets/plugin-bin-launcher.sh` is for CLI-installed plugins only.

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (keep under 19,900 chars — `wc -m`)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

These word counts are approximate and you can feel free to go longer if needed.

**Key patterns:**
- **Keep SKILL.md under 19,900 characters — measure with `wc -m`, not a line count.** This is the limit that actually bites: after auto-compaction Claude re-attaches each invoked skill truncated to that many characters and usually writes the truncation **back**, so a second compaction cannot recover the tail. A line count cannot protect it — a file can pass "under 500 lines" and still be twice over (this one is). If you're approaching the cap, add a layer of hierarchy and move whole phases into `references/`, which is not capped; front-load whatever must survive. See `references/official-guide-patterns.md` (SKILL.md Size) for the mechanism and the two ways a skill loses content entirely.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

For advanced patterns (setup/config, persistent data, on-demand hooks, Dynamic Context Injection, path variables such as `CLAUDE_SKILL_DIR`, relative markdown links), see `references/official-guide-patterns.md` (Practical Lessons and Advanced Skill Authoring Features sections).

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

A starting point, not the answer. The strongest signal comes later: if 2-3 independent eval runs all reinvent the same helper, that logic belongs in a script (see "Look for repeated work across test cases"). Don't over-script upfront. See [Script vs. Instruct decision framework](references/official-guide-patterns.md) ("When to Script vs. When to Instruct") for the full framework and examples.

**When you do bundle a script, design it for agent consumption** — non-interactive, `--help`-documented, structured output (JSON/CSV), helpful errors, meaningful exit codes, idempotent by default. A script that works fine for a human can be unusable for an agent. See [official-guide-patterns.md](references/official-guide-patterns.md) ("Designing Scripts for Agent Use") for the full conventions.

### Delivering Files the Skill Produces

This applies whichever environment you're authoring in — the risk lives in the runtime the *authored skill* runs under, not yours. If the skill produces a file for its user, its final step must **write it to a stated path and then present it** with whatever file-surfacing tool that runtime exposes. A path alone is not delivery everywhere — on ephemeral/remote sessions an unpresented file is silently lost. See `references/environments.md` → *Delivering files to the user*.

### Test Cases

**Pro Tip from the official guide: Iterate on a single task before expanding.** The most effective skill creators iterate on a single challenging task until Claude succeeds, then extract the winning approach into a skill. This leverages in-context learning and provides faster signal than broad testing. Once you have a working foundation, expand to multiple test cases for coverage.

After writing the skill draft, come up with 2-3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: [you don't have to use this exact language] "Here are a few test cases I'd like to try. Do these look right, or do you want to add more?" Then run them.

Per the official guide, effective testing covers three areas:
1. **Triggering tests** — Does the skill load at the right times? (obvious tasks, paraphrased requests, and confirming it doesn't trigger on unrelated topics)
2. **Functional tests** — Does the skill produce correct outputs? (valid outputs, API calls succeed, error handling works, edge cases covered)
3. **Performance comparison** — Does the skill actually improve results vs. baseline? (fewer tool calls, fewer user corrections, lower token usage)

Save test cases to `evals.json` in a **committed sibling** of the skill directory — `<skill-name>-evals/evals.json` — never inside the skill directory itself. The definitions are the durable regression suite (commit them; run in CI if the skill has a repo); an eval file inside the skill dir ships to users as dead weight.

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

Put results in `<skill-name>-workspace/`. **Put it where your instructions say to work — never as a sibling to the skill directory.** In Cowork your **file tools** need the absolute path of that directory: outputs if named (locally not the "Primary working directory", a private folder), else your working directory — never a bare path or an `outputs/` prefix. Your **shell** may spell that directory differently (locally `/sessions/<id>/mnt/outputs/`). Resolve both once (`<workspace, file-tool form>`, shell `<abs-workspace>`); give sub-agents both, labelled. On a plugin or marketplace install the skill directory is read-only, so a sibling path silently falls back to a scratchpad the user never sees — and on remote Cowork that is destroyed at session end. If you're unsure, ask. Organize it by iteration (`iteration-1/`, `iteration-2/`), and within that one directory per test case named for what it tests (`pdf-extraction/`, `multi-page-form/` — Step 1 explains the naming). Create directories as you go.

### Step 1: Spawn all runs (with-skill AND baseline) in the same turn

For each test case, spawn two subagents in the same turn — one with the skill, one without. This is important: don't spawn the with-skill runs first and then come back for baselines later. Launch everything at once so it all finishes around the same time.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Workspace, for Read/Write/Edit: <workspace, file-tool form>
- Workspace, for shell commands: <abs-workspace>
  (Use each exactly as given, and only with its own kind of tool — never convert one into the other. Where they are the same string, that is expected.)
- Save outputs to: <workspace, file-tool form>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
- Also write <workspace, file-tool form>/iteration-<N>/eval-<ID>/with_skill/outputs/user_notes.md: anything you were unsure about, workarounds you used, or things a human should review (write "none" if nothing)
- Also write <workspace, file-tool form>/iteration-<N>/eval-<ID>/with_skill/outputs/metrics.json: {"total_tool_calls": <n>, "errors_encountered": <n>} — your best count of tool calls made and errors hit
```

**Baseline run** (same prompt, but the baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, same two workspace lines, save to `<workspace, file-tool form>/iteration-<N>/eval-<ID>/without_skill/outputs/`, with the same user_notes.md and metrics.json instructions (absolute, for the same reason).
- **Improving an existing skill**: the old version. Before editing, snapshot the skill (`cp -r <skill-path> <abs-workspace>/skill-snapshot/`), then give the baseline subagent the same two workspace lines and the snapshot's path in both forms (it reads the skill with file tools, and the `cp` above used the shell form). Save to `<workspace, file-tool form>/iteration-<N>/eval-<ID>/old_skill/outputs/`.

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

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json` in each config directory (e.g., `eval-1/with_skill/grading.json`); a grader sub-agent gets that directory in both labelled forms, as in the executor template above — it writes with file tools and may run scripts. The grading.json expectations array must use the fields `text`, `passed`, and `evidence` (not `name`/`met`/`details` or other variants) — the viewer depends on these exact field names. For assertions that can be checked programmatically, write and run a script rather than eyeballing it — scripts are faster, more reliable, and can be reused across iterations. If a check is also something a user of the finished skill would benefit from running themselves (e.g., a `validate_X.py` or `smoke_test_X.sh`), bundle it in the skill's `scripts/` directory so the same code serves both the eval grader and end users.

**Every shell command below uses `<abs-workspace>` — the absolute path you resolved once at the start of this section.** Never rely on a working directory carrying between shell calls: on some surfaces each call is independent, so a `cd` in one call is gone by the next. An absolute path is correct on every surface, which is why you resolve once rather than `cd` first. A relative path also resolves against the *shell's* working directory, which under Cowork is not where your file tools write. The same applies to any path you put in a sub-agent dispatch prompt.

2. **Aggregate into benchmark** — run the aggregation script from the skill-creator directory:
   ```bash
   python -m scripts.aggregate_benchmark <abs-workspace>/iteration-N --skill-name <name>
   ```
   This produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens for each configuration, with mean ± stddev and the delta. If generating benchmark.json manually, see `references/schemas.md` for the exact schema the viewer expects, and order each with_skill run before its baseline counterpart in the `runs` array.

3. **Do an analyst pass** — read the benchmark data and surface patterns the aggregate stats might hide. See `agents/analyzer.md` (the "Analyzing Benchmark Results" section) for what to look for — things like assertions that always pass regardless of skill (non-discriminating), high-variance evals (possibly flaky), and time/token tradeoffs. Save the notes to `<workspace, file-tool form>/iteration-N/notes.json` (you write it with a file tool), then merge them into the benchmark: `python -m scripts.aggregate_benchmark <abs-workspace>/iteration-N --notes <abs-workspace>/iteration-N/notes.json` — otherwise the viewer's "Analysis Notes" section stays empty.

4. **Launch the viewer** with both qualitative outputs and quantitative data:
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <abs-workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <abs-workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   echo $! > <abs-workspace>/iteration-N/viewer.pid
   ```
   For iteration 2+, also pass `--previous-workspace <abs-workspace>/iteration-<N-1>`.

   **Cowork / headless environments:** If `webbrowser.open()` is not available or the environment has no display, use `--static <absolute-output-path>` to write a standalone HTML file instead of starting a server. When the user clicks "Submit All Reviews", the viewer displays the raw JSON in a copyable textarea (no file is downloaded — blob downloads blank the page in embedded viewers). The user pastes the JSON directly into the chat, or saves it themselves into the workspace as `feedback.json`. **Important: In static mode, you cannot read feedback.json from disk** — see `references/environments.md` (Cowork section) for how to handle the feedback loop.

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
kill "$(cat <abs-workspace>/iteration-N/viewer.pid)" 2>/dev/null && rm -f <abs-workspace>/iteration-N/viewer.pid
```

(The PID goes to a file because each bash invocation is a fresh shell — a `VIEWER_PID=$!` variable set at launch time is unset by the time you kill it, so the kill silently no-ops and the server keeps running. If the PID file is missing, `pkill -f generate_review.py` is the fallback.)

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
- [ ] If the skill produces a file for its user, the final step writes it to a stated path and then presents it (a path alone isn't delivery on every surface)
- [ ] Examples provided where helpful
- [ ] References clearly linked from SKILL.md
- [ ] SKILL.md stays under 19,900 characters (`wc -m`) — detailed content in references/, which is not capped
- [ ] No README.md inside the skill folder

You can run `python -m scripts.quick_validate <path-to-skill>` to check some of these automatically. **Run this and `check_portability` below from this skill's own directory** — the `python -m` module form resolves `scripts.` relative to the current directory, so it fails anywhere else. That directory is the one this file was loaded from; put the `cd` in the same command, since a shell's working directory may not carry between calls:

```bash
cd ${CLAUDE_SKILL_DIR} && python -m scripts.quick_validate <abs-path-to-skill>
```

If the shell says that directory does not exist, it sees these files under a different path (Cowork's host loop). If this file was re-read from disk after a compaction, the line above shows the variable unexpanded. Either way, find the directory from the shell's side and `cd` to the one that holds `scripts/`:

```bash
find / -path '*skill-creator-plus/scripts/quick_validate.py' -print -quit 2>/dev/null
```

Never skip `check_portability` or hand-roll the `.skill` zip because the scripts seem unreachable — locate them.

Also run `python -m scripts.check_portability <path-to-skill> --target <claude-code|claude-ai|cowork|all>` — a stdlib-only cross-runtime linter (no dependencies, runs in any environment). It flags constructs that break on the skill's target runtime: an over-cap `description`, subagent use (the Claude app's chat runtime has no sub-agent tool), `claude` CLI use (not on the chat runtime's PATH), browser/server assumptions (no display in Cowork or the chat runtime), third-party Python imports outside the stack Cowork preinstalls (each costs a `pip install` on every run, and a locked-down org can deny the egress that install needs), a `SKILL.md` over the 19,900-character post-compaction cap (`compaction-truncation-risk`), a workspace placed under a relative `outputs/` path, which Cowork refuses, nests, or loses depending on the lane (`outputs-prefix-relative`), a delivery tool named for only one Cowork lane (`delivery-tool-single-lane` — phrase delivery by outcome, naming no tool; naming both, capability-conditionally, is also acceptable and stays clean), and the deliverable itself gated on a delivery tool's availability (`delivery-conditional-deliverable`). Pass `--target` matching where the skill will run; `--strict` to gate.

If `cowork-harness` is installed, also run its two token-free static checks — `cowork-harness lint-skill --strict <skill-dir>` and `cowork-harness analyze-skill --strict <skill-dir>`. They're cheap and safe on any skill, and catch runtime bugs the checklist can't (host-path leaks, interactive-artifact write-backs lost under Cowork); their findings matter most for **Cowork-targeted** skills. Optional — skip silently if the tool isn't installed. See `references/environments.md` § *Testing Cowork-targeted skills with cowork-harness*.

### Package the Skill

Package the final skill into a distributable `.skill` file, from this skill's own directory (located as in *Validate* above):

```bash
cd <this-skill-dir> && python -m scripts.package_skill <abs-path-to-skill-folder> [output-dir]
```

**What the `.skill` file is:** a zip named `<skill-name>.skill` whose single top-level folder is the skill folder itself — `<skill-name>/SKILL.md`, `<skill-name>/scripts/…`, and so on — never files at the zip root. The folder name must equal the frontmatter `name` (validation runs first and refuses a mismatch), because installers key on that directory. Left out: `evals/` and `tests/` at the skill root, `__pycache__/`, `node_modules/`, `*.pyc`, `.DS_Store`, and every symlink (never followed, so nothing outside the folder is embedded); the script prints what it skipped.

`output-dir` is optional and defaults to the skill folder's parent, which is unwritable on a plugin or marketplace install — pass the destination explicitly, as an absolute path when a script will consume it.

**Never delete from the outputs directory.** Production denies `unlink`/`rmdir` there until the user approves it, so a "remove the stale copy and re-copy" step — the natural way to sync two directories — fails in production while succeeding in most test setups. Build once rather than staging a copy you have to refresh; if a file must change, overwrite it in place. Write the `.skill` file to a path you name in your reply — the workspace. (In Cowork `package_skill.py` runs in the shell, so give it the shell form, `<abs-workspace>/…`; state the path in your reply in the file-tool form the user sees. Never a bare filename, never an unnamed location.) Then present it: scan your available tools for one whose description says it sends or presents files to the user, and call it — the file is not delivered until you do, and stating the path is not a substitute — unless your instructions explicitly say that writing into a named folder delivers the file and not to send it as well. Only if no such tool exists, the path you already stated is the presentation. See `references/environments.md` → *Delivering files to the user* for why this two-step rule exists and which tool serves which surface. Packaging itself works everywhere Python does — never make it conditional on a presentation tool.

**Sending the `.skill` file is also how the user saves it.** Where the app renders a sent `.skill` as a card with a Save skill button, that button installs the whole package, scripts included, into the user's account — so sending it is never optional. If your tools also include one that saves a skill straight from the conversation, it carries `SKILL.md` alone: never use it instead of sending the file, and never for a skill that bundles scripts, references or assets. See `references/environments.md` → *Sandboxed sessions*.

---

## Environment-specific instructions

The core workflow above assumes sub-agents, a `claude` CLI on the shell's PATH, and a display. Route by what your **tool list** and instructions actually say, not by product name. If the tool list changes mid-conversation (a Claude app chat can be upgraded to a Cowork workspace), re-check, and re-read where the new instructions say to work. Before running test cases, the viewer, or packaging, read the matching parts of `references/environments.md`:

- **No tool that dispatches a sub-agent** (called `Agent`, or `Task` in older builds) → *Without sub-agents*: run test cases inline yourself, skip baselines, benchmarking and blind comparison.
- **No `claude` CLI** (`command -v claude` finds nothing, or you have no shell) → skip description optimization.
- **No display** (any container, remote shell, Cowork or chat session — assume none unless you are in a terminal on the user's own machine) → the static viewer and paste-back bullets in *Sandboxed sessions*, which apply to any session without a display.
- **Your instructions say the user cannot see your working directory, name an outputs directory for the user's files, or describe sending files to the user** — not a terminal on the user's own machine (Cowork, cloud or local, and the chat runtime) → *Sandboxed sessions* for paths and delivery. That does not tell you whether you have sub-agents; the first bullet decides that.
- **Device tools** — names containing `device_`, often deferred (load them with ToolSearch) → same section: a path on the user's computer goes only to the device file tools, after a folder is granted (request access with the folder-access tool, or ask the user); your own Write to it lands in the cloud container.

These combine: a cloud Cowork session typically has sub-agents but no display; the chat runtime typically has neither.

---

## Reference files

The agents/ directory contains instructions for specialized subagents. Read them when you need to spawn the relevant subagent.

- `agents/grader.md` — How to evaluate assertions against outputs
- `agents/comparator.md` — How to do blind A/B comparison between two outputs
- `agents/analyzer.md` — How to analyze why one version beat another

The references/ directory has additional documentation:
- `references/schemas.md` — JSON structures for evals.json, grading.json, etc.
- `references/official-guide-patterns.md` — Anthropic's official best practices: use case categories, description formula, five skill patterns, instructions best practices, technical rules, troubleshooting guide, and quick checklist. **Consult this when designing a new skill or diagnosing issues with an existing one.**
- `references/environments.md` — capability adaptations: no sub-agents, no display, sandboxed-session paths and delivery (see *Environment-specific instructions*)
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

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you have no display, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.

Good luck!
