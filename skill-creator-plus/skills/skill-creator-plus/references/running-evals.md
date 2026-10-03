# Running evals

Read this before Step 1. It continues SKILL.md's *Run, review, improve*, which keeps the five-step skeleton and the workspace rules; this file has the detail.

**`<this-skill-dir>`** below is the skill directory you resolved in SKILL.md (*Validate, package and deliver*): the directory holding this skill's `scripts/` and `eval-viewer/`, as your shell sees it. `<abs-workspace>` and `<workspace, file-tool form>` are the two workspace forms SKILL.md has you resolve once (*The workspace*).

## Contents

- [Test cases](#test-cases)
- [Running and evaluating test cases](#running-and-evaluating-test-cases)
  - [Step 1: Spawn all runs (with-skill AND baseline) in the same turn](#step-1-spawn-all-runs-with-skill-and-baseline-in-the-same-turn)
  - [Step 2: While runs are in progress, draft assertions](#step-2-while-runs-are-in-progress-draft-assertions)
  - [Step 3: As runs complete, capture timing data](#step-3-as-runs-complete-capture-timing-data)
  - [Step 4: Grade, aggregate, and launch the viewer](#step-4-grade-aggregate-and-launch-the-viewer)
  - [What the user sees in the viewer](#what-the-user-sees-in-the-viewer)
  - [Step 5: Read the feedback](#step-5-read-the-feedback)
- [Improving the skill](#improving-the-skill)
  - [How to think about improvements](#how-to-think-about-improvements)
  - [The iteration loop](#the-iteration-loop)
- [Advanced: Blind comparison](#advanced-blind-comparison)
- [The core loop, once more](#the-core-loop-once-more)

## Test cases

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

Put results in the `<skill-name>-workspace/` SKILL.md has you set up (*The workspace*): resolve both forms once, organize it by iteration (`iteration-1/`, `iteration-2/`), and within that one directory per test case named for what it tests (`pdf-extraction/`, `multi-page-form/` — Step 1 explains the naming). Create directories as you go.

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
- Save outputs to: <workspace, file-tool form>/iteration-<N>/<eval-name>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
- Also write <workspace, file-tool form>/iteration-<N>/<eval-name>/with_skill/outputs/user_notes.md: anything you were unsure about, workarounds you used, or things a human should review (write "none" if nothing)
- Also write <workspace, file-tool form>/iteration-<N>/<eval-name>/with_skill/outputs/metrics.json: {"total_tool_calls": <n>, "errors_encountered": <n>} — your best count of tool calls made and errors hit
```

**Baseline run** (same prompt, but the baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, same two workspace lines, save to `<workspace, file-tool form>/iteration-<N>/<eval-name>/without_skill/outputs/`, with the same user_notes.md and metrics.json instructions (absolute, for the same reason).
- **Improving an existing skill**: the old version. Before editing, snapshot the skill (`cp -r <skill-path> <abs-workspace>/skill-snapshot/`), then give the baseline subagent the same two workspace lines and the snapshot's path in both forms (it reads the skill with file tools, and the `cp` above used the shell form). Save to `<workspace, file-tool form>/iteration-<N>/<eval-name>/old_skill/outputs/`.

Write an `eval_metadata.json` for each test case (assertions can be empty for now). Give each eval a descriptive name based on what it's testing — not just "eval-0". Use this name for the directory too: it is the `<eval-name>` in the paths above. If this iteration uses new or modified eval prompts, create these files for each new eval directory — don't assume they carry over from previous iterations.

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

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json` in each config directory (e.g., `<eval-name>/with_skill/grading.json`); a grader sub-agent gets that directory in both labelled forms, as in the executor template above — it writes with file tools and may run scripts. The grading.json expectations array must use the fields `text`, `passed`, and `evidence` (not `name`/`met`/`details` or other variants) — the viewer depends on these exact field names. For assertions that can be checked programmatically, write and run a script rather than eyeballing it — scripts are faster, more reliable, and can be reused across iterations. If a check is also something a user of the finished skill would benefit from running themselves (e.g., a `validate_X.py` or `smoke_test_X.sh`), bundle it in the skill's `scripts/` directory so the same code serves both the eval grader and end users.

**Every shell command below uses `<abs-workspace>` — the absolute path you resolved once (SKILL.md, *The workspace*).** Never rely on a working directory carrying between shell calls: on some surfaces each call is independent, so a `cd` in one call is gone by the next. An absolute path is correct on every surface, which is why you resolve once rather than `cd` first. A relative path also resolves against the *shell's* working directory, which in a cloud or local session is not where your file tools write. The same applies to any path you put in a sub-agent dispatch prompt.

2. **Aggregate into benchmark** — run the aggregation script from this skill's directory, with the `cd` in the same command (the `-m scripts.` form resolves against the current directory):
   ```bash
   cd <this-skill-dir> && python -m scripts.aggregate_benchmark <abs-workspace>/iteration-N --skill-name <name>
   ```
   This produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens for each configuration, with mean ± stddev and the delta. If generating benchmark.json manually, see `references/schemas.md` for the exact schema the viewer expects, and order each with_skill run before its baseline counterpart in the `runs` array.

3. **Do an analyst pass** — read the benchmark data and surface patterns the aggregate stats might hide. See `agents/analyzer.md` (the "Analyzing Benchmark Results" section) for what to look for — things like assertions that always pass regardless of skill (non-discriminating), high-variance evals (possibly flaky), and time/token tradeoffs. Save the notes to `<workspace, file-tool form>/iteration-N/notes.json` (you write it with a file tool), then merge them into the benchmark: `cd <this-skill-dir> && python -m scripts.aggregate_benchmark <abs-workspace>/iteration-N --notes <abs-workspace>/iteration-N/notes.json` — otherwise the viewer's "Analysis Notes" section stays empty.

4. **Launch the viewer** with both qualitative outputs and quantitative data:
   ```bash
   nohup python <this-skill-dir>/eval-viewer/generate_review.py \
     <abs-workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <abs-workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   echo $! > <abs-workspace>/iteration-N/viewer.pid
   ```
   For iteration 2+, also pass `--previous-workspace <abs-workspace>/iteration-<N-1>`.

   **Sandboxed sessions / headless environments:** If `webbrowser.open()` is not available or the environment has no display, use `--static <absolute-output-path>` to write a standalone HTML file instead of starting a server. When the user clicks "Submit All Reviews", the viewer displays the raw JSON in a copyable textarea (no file is downloaded — blob downloads blank the page in embedded viewers). The user pastes the JSON directly into the chat, or saves it themselves into the workspace as `feedback.json`. **Important: In static mode, you cannot read feedback.json from disk** — see `references/environments.md` → *Sandboxed sessions* for how to handle the feedback loop.

Note: please use generate_review.py to create the viewer; there's no need to write custom HTML.

**Put the outputs in front of the user before your own analysis, in every environment** — Claude Code included, not only sandboxed sessions. The analyst pass above writes notes for the viewer; it is not your verdict. Generate the viewer and hand it to the user before you judge the outputs, report conclusions, or start revising the skill: the human needs to form their own opinion first.

5. **Tell the user** something like: "I've opened the results in your browser. There are two tabs — 'Outputs' lets you click through each test case and leave feedback, 'Benchmark' shows the quantitative comparison. When you're done, come back here and let me know."

### What the user sees in the viewer

The "Outputs" tab shows one test case at a time:
- **Prompt**: the task that was given
- **Output**: the files the skill produced, rendered inline where possible
- **Previous Output** (iteration 2+): collapsed section showing last iteration's output
- **Formal Grades** (if grading was run): collapsed section showing assertion pass/fail
- **Feedback**: a textbox that auto-saves as they type (server mode only; in static mode nothing is saved until they submit)
- **Previous Feedback** (iteration 2+): their comments from last time, shown below the textbox

The "Benchmark" tab shows the stats summary: pass rates, timing, and token usage for each configuration, with per-eval breakdowns and analyst observations.

Navigation is via prev/next buttons or arrow keys. When done, they click "Submit All Reviews". In server mode that saves all feedback to `feedback.json`; in static mode it shows the JSON in a copyable box for the user to paste back into the chat, and no file is written.

### Step 5: Read the feedback

When the user tells you they're done, read the feedback: in server mode, `feedback.json` in the iteration directory; in static mode, the JSON the user pasted into the chat (or the `feedback.json` they saved into the workspace themselves — none appears on its own). Either way it looks like this:

```json
{
  "reviews": [
    {"run_id": "pdf-extraction-with_skill", "feedback": "the chart is missing axis labels", "timestamp": "..."},
    {"run_id": "multi-page-form-with_skill", "feedback": "", "timestamp": "..."},
    {"run_id": "scanned-receipt-with_skill", "feedback": "perfect, love this", "timestamp": "..."}
  ],
  "status": "complete"
}
```

Empty feedback means the user thought it was fine. Focus your improvements on the test cases where the user had specific complaints.

Kill the viewer server (server mode) when you're done with it:

```bash
kill "$(cat <abs-workspace>/iteration-N/viewer.pid)" 2>/dev/null && rm -f <abs-workspace>/iteration-N/viewer.pid
```

(The PID goes to a file because each bash invocation is a fresh shell — a `VIEWER_PID=$!` variable set at launch time is unset by the time you kill it, so the kill silently no-ops and the server keeps running. If the PID file is missing, `pkill -f generate_review.py` is the fallback.)

## Improving the skill

This is the heart of the loop. You've run the test cases, the user has reviewed the results, and now you need to make the skill better based on their feedback.

### How to think about improvements

1. **Generalize from the feedback.** The big picture thing that's happening here is that we're trying to create skills that can be used a million times (maybe literally, maybe even more who knows) across many different prompts. Here you and the user are iterating on only a few examples over and over again because it helps move faster. The user knows these examples in and out and it's quick for them to assess new outputs. But if the skill you and the user are codeveloping works only for those examples, it's useless. Rather than put in fiddly overfitty changes, or oppressively constrictive MUSTs, if there's some stubborn issue, you might try branching out and using different metaphors, or recommending different patterns of working. It's relatively cheap to try and maybe you'll land on something great.

2. **Keep the prompt lean.** Remove things that aren't pulling their weight. Make sure to read the transcripts, not just the final outputs — if it looks like the skill is making the model waste a bunch of time doing things that are unproductive, you can try getting rid of the parts of the skill that are making it do that and seeing what happens.

3. **Explain the why.** Try hard to explain the **why** behind everything you're asking the model to do. Today's LLMs are *smart*. They have good theory of mind and when given a good harness can go beyond rote instructions and really make things happen. Even if the feedback from the user is terse or frustrated, try to actually understand the task and why the user is writing what they wrote, and what they actually wrote, and then transmit this understanding into the instructions. If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag — if possible, reframe and explain the reasoning so that the model understands why the thing you're asking for is important. That's a more humane, powerful, and effective approach.

4. **Look for repeated work across test cases.** Read the transcripts from the test runs and notice if the subagents all independently wrote similar helper scripts or took the same multi-step approach to something. If all 3 test cases resulted in the subagent writing a `create_docx.py` or a `build_chart.py`, that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and tell the skill to use it. This saves every future invocation from reinventing the wheel. This works in both directions: scripts you bundle for end users (validators, smoke tests) can also be reused as eval-time grader assertions in later iterations. See `references/official-guide-patterns.md` ("When to Script vs. When to Instruct") for guidance on what belongs in a script vs. what should stay as instructions.

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

## Advanced: Blind comparison

For situations where you want a more rigorous comparison between two versions of a skill (e.g., the user asks "is the new version actually better?"), there's a blind comparison system. Read `agents/comparator.md` and `agents/analyzer.md` for the details. The basic idea is: give two outputs to an independent agent without telling it which is which, and let it judge quality. Then analyze why the winner won. When you run more than one comparison round, alternate which version is labeled A and which is B between rounds, and record the mapping (e.g. `comparison_mapping.json` next to each comparator output) so results can be unblinded later — judges drift toward the first-presented output, and counterbalancing cancels that bias.

This is optional, requires subagents, and most users won't need it. The human review loop is usually sufficient.

## The core loop, once more

- Figure out what the skill is about
- Draft or edit the skill
- Run claude-with-access-to-the-skill on test prompts
- With the user, evaluate the outputs:
  - Create benchmark.json and run `eval-viewer/generate_review.py` to help the user review them
  - Run quantitative evals
- Repeat until you and the user are satisfied
- Package the final skill and return it to the user.

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you have no display, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.
