---
name: skill-creator-plus
description: Create, test, evaluate, and improve Claude skills — and answer questions about how skills work. Use for "create a skill", "make a skill for", "write a SKILL.md", "turn this into a skill", "run evals", "test/benchmark my skill", "optimize my skill description", "improve triggering", "A/B test my skill", "blind comparison", packaging for distribution, editing an existing skill, or reviewing skill quality. Also for a single narrow question about skill mechanics, however small — referencing a bundled script or reference doc, path variables, frontmatter fields, directory layout, size limits, or what breaks across Claude Code, Claude.ai and Cowork.
license: MIT
metadata:
  author: Yaniv Golan
  version: "0.17.0"
---

# Skill Creator Plus

A skill for creating new skills, iteratively improving them, and answering questions about how skills work.

The loop: decide what the skill should do → draft it → run test prompts with the skill → help the user evaluate the results, qualitatively (the eval viewer) and quantitatively (benchmarks) → rewrite from their feedback → repeat, then expand the test set. Figure out where the user is in this loop and join them there: "I want a skill for X" starts at the top; an existing draft jumps straight to eval/iterate. Order is flexible; once the skill is done you can run the description improver to sharpen its triggering. **Before running any test case, read `references/running-evals.md`.**

Calibrate jargon to the person: "evaluation" and "benchmark" are borderline but OK; explain "JSON" or "assertion" unless they've shown they know them.

**If a section this file refers to seems to be missing, it was truncated — re-read `SKILL.md` from disk before continuing.** Compaction cuts the tail and writes the cut back, so what's in context can be a partial copy. (This works only when a truncation marker is present; it cannot detect a skill dropped whole by the combined cap.)

### The one-pass path

Often the user wants a working skill now, not an eval report. That is a legitimate route, not a shortcut — take it when they ask for the skill itself, or say they don't want evals:

1. **Draft** the skill (*Capture Intent* → *Write the SKILL.md*, below).
2. **Smoke-test every script you bundled**, directly: run it on synthetic input with the problems planted (malformed rows, wrong delimiter, unusual encoding, empty and header-only files, a missing file), plus one realistic case. A script that only ever ran on clean input is untested. When a smoke test fails, work out whether the script or the *test* is wrong before changing either — a synthetic fixture is a guess too. A check worth keeping belongs in the skill's own `scripts/`, so its users can run it as well.
3. **Validate**: `quick_validate` then `check_portability` (see *Validate, package and deliver*, which says how to find them; never hand-roll the package).
4. **Package and deliver** it (same section).
5. **Then offer** the eval loop (read `references/running-evals.md` before Step 1) and description optimization as follow-ups.

Steps 2 and 3 *are* the verification when you skip evals — shipping without eval evidence is fine, shipping with nothing exercised is not.

## Environment-specific instructions

**No sub-agent tool, or instructions saying where to work or how files reach the user? Read `references/environments.md` first** — paths and delivery differ per runtime. The core workflow assumes sub-agents, a `claude` CLI on the shell's PATH, and a display. Route by what your **tool list** and instructions actually say, not by product name. If the tool list changes mid-conversation (a conversation can start a cloud session partway through, when it needs a shell or files), re-check, and re-read where the new instructions say to work.

- **No tool that dispatches a sub-agent** (called `Agent`, or `Task` in older builds) → *Without sub-agents*: run test cases inline yourself, skip baselines, benchmarking and blind comparison.
- **No `claude` CLI** (`command -v claude` finds nothing, or you have no shell) → skip description optimization.
- **No display** (any container, remote shell, or sandboxed session — assume none unless you are in a terminal on the user's own machine) → *Viewer and feedback* in *Sandboxed sessions*: the static viewer and paste-back, which apply to any session without a display.
- **Your instructions say the user cannot see your working directory, name an outputs directory for the user's files, or describe sending files to the user** — not a terminal on the user's own machine (cloud and local sessions, and the chat runtime) → *Sandboxed sessions* for paths and delivery. That does not tell you whether you have sub-agents; the first bullet decides that.
- **Device tools** — names containing `device_`, often deferred (load them with ToolSearch) → same section: a path on the user's computer goes only to the device file tools, after a folder is granted (request access with the folder-access tool, or ask the user); your own Write to it lands in the cloud container.

These combine: a cloud session typically has sub-agents but no display; the chat runtime typically has neither.

## Answering a question about skills

A narrow question (referencing a bundled script, a frontmatter field, size limits, what breaks across runtimes) gets a direct answer, not the build loop. Open the matching reference via its table of contents and answer from it — `references/official-guide-patterns.md` for authoring, `references/advanced-features.md` for Claude Code mechanics, `references/environments.md` for cloud, local and chat sessions, `assets/skill-script-invocation.md` for script paths — keeping its hedges.

---

## Creating a skill

### Capture Intent

Start by understanding the user's intent. If the conversation already contains the workflow ("turn this into a skill"), extract answers from it first — tools used, sequence of steps, corrections the user made, input/output formats — and have the user fill the gaps and confirm.

1. What should this skill enable Claude to do?
2. When should it trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Which use case category — Document & Asset Creation, Workflow Automation, or MCP Enhancement? See `references/official-guide-patterns.md` (*Use Case Categories*; *Expanded Skill Type Taxonomy* has nine finer types).
5. Test cases? Objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit; subjective ones (writing style, art) often don't. Suggest a default, but let the user decide.

### Define Success Criteria

Before writing, help the user say what "working" looks like — aspirational targets that keep the loop focused. Cover **quantitative** (triggers reliably? fewer tool calls than without? no failed calls?) and **qualitative** (finishes without redirecting Claude? consistent across sessions?). See `references/official-guide-patterns.md` (*Success Criteria*).

### Interview and Research

Ask about edge cases, input/output formats, example files, success criteria and dependencies before writing test prompts. If MCPs help with research (docs, similar skills), research in parallel via subagents if available, otherwise inline.

### Write the SKILL.md

**Where the skill directory goes:** somewhere the user can keep it — a location in their project, confirmed with them if unclear. Never inside this plugin's own directory (read-only on a plugin install), and never a scratch directory. **Build it in one place and never keep a second copy to sync.** Authoring is mostly shell work, and the shell's cwd is not the file tools' — so name the destination once and address it per family: in a sandboxed session, build in the directory your instructions designate for your work (outputs if named, else your working directory), by absolute path, each family in its own spelling. `references/environments.md` has the mechanism.

**Portable fields** (every agentskills.io host):

- **name**: kebab-case, must match the folder name
- **description**: how agents decide whether to load the skill. Write a **trigger, not a summary**: `[What it does] + [When to use it] + [Key capabilities]`; under 1024 characters, no XML tags, assertive (models undertrigger). On portable hosts it is the only discovery text, so it must stand alone. See `references/official-guide-patterns.md` (*Description Field Formula*).
- Optional: `license`, `metadata` (`author`, `version`), `compatibility` (≤500 chars), `allowed-tools`. **When the user hasn't specified**, omit `license` and `metadata.author` rather than inventing them — a licence or byline you made up is a claim on their behalf. Default `metadata.version` to `0.1.0`.

**Claude-specific fields** (`when_to_use`, `disallowed-tools`, `model`, `context: fork`, `argument-hint`, path variables, …) are silently ignored elsewhere; see `references/official-guide-patterns.md` (*Claude-specific frontmatter: what these fields actually do*). **Never put load-bearing trigger info in `when_to_use`** — non-Claude hosts ignore it, and in a local session it is only half-visible even on Claude. Tool fields grant and restrict but never prompt; for a project skill (`.claude/skills/`) the real gate is **workspace trust**, accepted once per folder.

### Skill Writing Guide

A skill is a folder: `SKILL.md` plus optional `scripts/` (deterministic work), `references/` (read on demand) and `assets/` (used in output). For several domains, one reference per variant, so Claude reads only the relevant one.

**Reaching a bundled script:** the skill-directory variable (`CLAUDE_SKILL_DIR`, braced) is a load-time substitution into `SKILL.md` text only — it arrives literally in a `references/*.md` and is the empty string in a shell; CWD is never the skill directory. **Don't hand-write the stanza** — paste it from `assets/skill-script-invocation.md` (stanza B outside Claude Code). Not a `bin/` launcher: no plugin's own launcher has been seen on a local session's shell PATH (the cloud case is untested), and a top-level `bin/` makes a plugin unpublishable through claude.ai organization settings. `assets/plugin-bin-launcher.sh` is for CLI-installed plugins only.

**Keep SKILL.md under 19,900 characters — measure with `wc -m`, not a line count.** After auto-compaction Claude re-attaches each invoked skill truncated to that many characters and usually writes the truncation **back**, so a second compaction cannot recover the tail. Move whole phases into `references/` (not capped; give long ones a table of contents), say when to read each, and front-load what must survive. See `references/official-guide-patterns.md` (*SKILL.md Size*); hooks and path variables: `references/advanced-features.md`.

Rules and structure: `references/official-guide-patterns.md` (*Technical Rules*, *Five Skill Patterns*). Skills must not contain malware, exploit code, or anything that would surprise the user if described, and must not be misleading or built to facilitate unauthorized access.

Write in the imperative, specific and actionable: actual commands and common failure modes, with error handling. Show an exact template for a fixed output format, and an input → output example for a style.

### Writing Style

Explain the **why** behind instructions instead of heavy-handed MUSTs. Make skills general, not narrow to specific examples. Draft, then review with fresh eyes. Don't state the obvious, build a Gotchas section (highest-signal content), avoid railroading Claude — `references/official-guide-patterns.md` (*Practical Lessons from Anthropic's Internal Use*).

### Script vs. Instruct

Script what is deterministic, checkable by a fixed rule or exit code, or boilerplate Claude would re-derive every run; instruct what needs judgment or flexible recovery. Don't over-script up front — the strongest signal is 2-3 eval runs reinventing the same helper. Design scripts for agents: non-interactive, `--help`, structured output, meaningful exit codes. See `references/official-guide-patterns.md` (*When to Script vs. When to Instruct*, *Designing Scripts for Agent Use*).

### Delivering Files the Skill Produces

This applies whichever environment you're authoring in — the risk lives in the runtime the *authored skill* runs under, not yours. If the skill produces a file for its user, its final step must **write it to a stated path and then present it** with whatever file-surfacing tool that runtime exposes. A path alone is not delivery everywhere — on ephemeral/remote sessions an unpresented file is silently lost. See `references/environments.md` → *Delivering files to the user*.

### Test Cases

Write 2-3 realistic test prompts — what a real user would say — and check them with the user. Save them to `evals.json` in a **committed sibling** of the skill directory — `<skill-name>-evals/evals.json` — never inside the skill directory, where it ships to users. Format: `references/running-evals.md` (*Test cases*).

### The workspace

Put results in `<skill-name>-workspace/`. **Put it where your instructions say to work.** In Claude Code a sibling of a skill directory you own is fine; never beside an installed (read-only) skill — in a sandboxed session see `references/environments.md`. There your **file tools** need the absolute path of that directory: outputs if named (locally not the "Primary working directory", a private folder), else your working directory — never a bare path or an `outputs/` prefix. Your **shell** may spell that directory differently (locally `/sessions/<id>/mnt/outputs/`). Resolve both once (`<workspace, file-tool form>`, shell `<abs-workspace>`); give sub-agents both, labelled. In a sandboxed session an installed skill's directory is read-only, so a sibling path silently falls back to a scratchpad the user never sees — and in a cloud session that is destroyed at session end; in Claude Code it is writable but replaced on update, so never there either. If you're unsure, ask.

## Run, review, improve

One continuous sequence; don't stop partway. Do NOT use `/skill-test` or any other testing skill. **Read `references/running-evals.md` before Step 1** — templates and commands, written with `<this-skill-dir>` (see *Validate, package and deliver*).

1. **Spawn all runs** — per test case, a with-skill and a baseline sub-agent **in the same turn**, never baselines later.
2. **Draft assertions** while they run; explain them to the user.
3. **Capture timing** — `total_tokens` and `duration_ms` exist only in the task notification, so save them to the run's `timing.json` as each run completes.
4. **Grade each run against its assertions, aggregate into a benchmark** (pass rate, time and tokens, with and without the skill), **and show the user the viewer** (`eval-viewer/generate_review.py`; static mode with no display) before your own analysis.
5. **Read the feedback, improve, rerun** into `iteration-<N+1>/` until the user is happy or progress stops.

## Description optimization

After creating or improving a skill, offer to optimize its description: ~20 realistic trigger eval queries, reviewed by the user, then `scripts/run_loop.py` (real `claude -p` calls, from `<this-skill-dir>`). Apply the resulting `best_description`. Read `references/description-optimization.md` first. Needs the `claude` CLI (`command -v claude`).

## Validate, package and deliver

Detail and checklist: `references/validate-and-package.md`. The `python -m` form resolves `scripts.` against the current directory, so `cd` to this skill's directory in the same command:

```bash
cd ${CLAUDE_SKILL_DIR} && python -m scripts.quick_validate <abs-path-to-skill>
```

If the shell says that directory does not exist (an older local Desktop build), or the line shows the variable unexpanded (when invoked before the conversation has started its cloud session, typically as its first message, and on a re-read from disk after a compaction — the `cd` then silently lands in home), find it from the shell's side and `cd` to the one holding `scripts/`:

```bash
find / -path '*skill-creator-plus/scripts/quick_validate.py' -print -quit 2>/dev/null
```

The directory that works is **`<this-skill-dir>`**; the references use it. Never skip a check or hand-roll the `.skill` zip because the scripts seem unreachable — locate them.

```bash
cd <this-skill-dir> && python -m scripts.check_portability <abs-path-to-skill> --target <claude-code|claude-ai|cowork|all>
cd <this-skill-dir> && python -m scripts.package_skill <abs-path-to-skill-folder> <output-dir>
```

Pass `<output-dir>` explicitly (the default is unwritable in a sandboxed session and replaced on update in Claude Code): the shell form, `<abs-workspace>/…`, in a cloud or local session; name the file-tool form in your reply. **Deliver in two steps**: write it to that stated path, then call any tool whose description says it sends or presents files to the user — the file is not delivered until you do, and stating the path is not a substitute — unless your instructions explicitly say that writing into a named folder delivers the file and not to send it as well. Only with no such tool is the stated path the presentation. Never make packaging conditional on that tool. **Don't delete from the outputs directory** — a delete can be refused until the user approves it; overwrite in place.

**Sending the `.skill` file is also how the user saves it**: its card's Save skill button (shown only when the user's org allows skill creation) installs the whole package, scripts included, so sending it is never optional. A tool that saves a skill from the conversation carries `SKILL.md` alone — never a substitute.

## Reference files

- `references/running-evals.md` — Steps 1–5, viewer, feedback, improving, blind comparison
- `references/validate-and-package.md` — checklist, validators, packaging, delivery
- `references/environments.md` — no sub-agents, no display, sandboxed sessions
- `references/official-guide-patterns.md` — Anthropic's guidance, plus this project's marked additions
- `references/advanced-features.md` — Claude-specific features, runtime mechanics
- `references/description-optimization.md`, `references/schemas.md`
- `agents/grader.md`, `agents/comparator.md`, `agents/analyzer.md` — sub-agent instructions
- `assets/skill-script-invocation.md`, `assets/plugin-bin-launcher.sh`, `assets/eval_review.html` (trigger-eval review)
- `scripts/check_portability.py` — cross-runtime lint
