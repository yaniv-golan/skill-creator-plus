# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Delivery guidance for skills that produce a file for their user** — a new *Delivering Files the Skill Produces* section in `SKILL.md` (plus a checklist item), expanded in `references/environments.md` → *Delivering files to the user*. Two ordered steps, phrased by outcome and naming no tool: **(1)** write the deliverable to a stated path, unconditionally, and never to cwd — in Cowork, cwd is a scratchpad the user can't see; **(2)** then scan your available tools for one whose description says it sends or presents files to the user, and **call it if one exists** — stating the path is not a substitute. Only if none exists, state the path. This matters because Cowork's two lanes deliver differently: on the local lane the write plus a stated path completes delivery, but on remote cloud-container Cowork the session runs in a sandbox destroyed when the session ends, so a file that is written and never presented is **silently lost**. The guidance is unconditional on the author's own environment — the risk lives in the runtime the *authored* skill will run under. `present_files` and `SendUserFile` appear only as a recognition aid for reading a transcript, never as text to copy into an authored skill; `device_commit_files` is never named at all. Sources are limited to publicly checkable ones: `anthropics/claude-code` issues #50041, #76344, #36438, and Anthropic's Cowork architecture overview.
- **Two `check_portability.py` rules** (both warning). `delivery-tool-single-lane` fires when a skill names one delivery-tool family (`present_files` or `SendUserFile`) anywhere in its text but not the other, stranding the Cowork lane served by the missing one — phrasing delivery by outcome and naming neither is the recommended pattern and stays clean, as does naming both. `delivery-conditional-deliverable` fires when a clause gates *production* of the artifact on a delivery tool's availability (a skip/omit phrase plus a production verb), which is the real upstream failure mode; legitimate capability-conditional *presentation* is not flagged. Both are suppressed per-file by a `portability-allow: file-delivery-tool` marker in comment context. A self-lint test pins this skill's own wording against both rules.
- **Two harness scenarios exercise the delivery guidance above at runtime, one per Cowork lane.** `harness/scenarios/create-skill.yaml` (local lane) now asserts `present_files_called: true` — hard, evidence-backed proof the packaged file was actually surfaced, not just written. `harness/scenarios/remote-delivery.yaml` (new; remote lane, where `user_visible_artifact` and `present_files_called` are rejected at load time because no delivery tool exists there and the harness's transcript can't see tool calls at all) instead grades via `semantic_matches` whether the deliverable was written to an explicitly stated, user-reachable location and that location was communicated — the observable, lane-appropriate signal. Both are live-only and never a PR gate; CI load-checks them. Neither assertion has yet been observed passing on a live run — both are marked as such inline, so a first red is investigated rather than assumed to be a regression.
- **A token-free scenario load gate in CI** (`cowork-harness record harness/scenarios/ --dry-run --quiet`). `lint` only warns on an unknown key, so a scenario that lints clean can still fail to load — a green lint is not evidence the suite runs.

### Changed
- **cowork-harness pin 1.2.0 → 1.16.0** across CI, `docs/DEVELOPMENT.md`, `harness/README.md`, and the shipped `references/environments.md` (which still advertised a 1.1.0 floor to every installed agent). `lane:` requires ≥ 1.14.0.

### Fixed
- **The packaging step no longer names a file-delivery tool, or attributes one to the wrong surface.** `SKILL.md` told authors to present the packaged `.skill` via `present_files` "(Claude.ai)" — a hardcoded tool name plus an unsupported attribution; no public evidence indicates Claude.ai chat serves `present_files`, and the only confirmed server of it is Cowork's desktop-local lane, where it is MCP-namespaced as `mcp__cowork__present_files`. The step now follows the delivery guidance above and names no tool. The `[0.5.0]` entry below repeats the same misattribution and is left as shipped, since released entries are a historical record.

## [0.7.0] - 2026-07-16

### Fixed
- **`quick_validate.py` / `package_skill.py` no longer require PyYAML at runtime.** They imported PyYAML, which Cowork's container image lacks and its default-deny egress can't `pip install` — so both crashed (or the agent fell back to hand-validation) when the skill ran under Cowork. Replaced with a stdlib-only `scripts/frontmatter.py` parser covering the frontmatter YAML subset (scalars, nested mappings, block/flow sequences, block scalars) and rejecting exotic constructs (anchors/aliases/tags/merge/multi-doc) with a clear error. Behavior is identical across runtimes because there's a single parser; a differential test (`tests/test_frontmatter.py`) keeps it aligned with `yaml.safe_load`. PyYAML is now a test-only dependency. quick_validate exit code `2` is retired to "reserved".

### Added
- **`scripts/check_portability.py`** — a stdlib-only cross-runtime portability linter. Flags constructs that break on a skill's target runtime: over-cap `description`, subagent use (absent on Claude.ai), `claude` CLI use (absent on Claude.ai), browser/server assumptions (no display in Cowork/Claude.ai), and third-party Python imports in bundled scripts (Cowork's sandbox lacks them and can't `pip install`). `--target claude-code|claude-ai|cowork|all`, `--json`, `--strict`.
- **`harness/`** — a cowork-harness dogfood suite that regression-tests this skill under Claude Cowork's runtime, plus a token-free CI lane (`.github/workflows/harness.yml`).

## [0.6.0] - 2026-07-08

### Changed
- **Eval definitions now live outside the skill directory.** SKILL.md and `references/schemas.md` previously told authors to save `evals/evals.json` *inside* the skill directory (inherited verbatim from the upstream Anthropic skill-creator, whose `schemas.md` still says "within the skill directory"). Plugin/marketplace installs copy the whole skill directory into every client, so an eval file inside it shipped the answer key (prompts + `expected_output` + assertions) to runtime and added dead weight to every install. New convention, split by lifecycle: eval **definitions** → `<skill-name>-evals/` committed sibling (regression suite; CI-run if the skill has a repo); eval **results** → `<skill-name>-workspace/` gitignored sibling (ephemeral); the skill directory → pure runtime content only. `package_skill.py`'s root `evals/`/`tests/` exclusion is retained as belt-and-suspenders. See `references/schemas.md` → "Where evals live".

## [0.5.0] - 2026-06-11

### Fixed
- **`aggregate_benchmark.py`: benchmark.json `runs` array was corrupted by loop-variable shadowing** (regression introduced alongside the 0.4.1 `runs_per_configuration` fix) — the viewer's Benchmark tab silently showed empty data. Also: IndexError on stray non-`eval-N` directories, token counts no longer fall back to character counts, tokens are read from grading.json timing AND timing.json, pass-rate delta is now percentage points, and partially-graded evals produce a loud warning.
- **`run_eval.py`: parallel workers no longer share `.claude/commands/`** — each run gets an isolated temp project root, eliminating cross-contaminated trigger detection that biased optimization. Subprocess failures and no-output timeouts are now reported as errors and excluded from trigger rates instead of being scored as "did not trigger"; if every run errors the CLI exits 1.
- **`run_loop.py --holdout 0` no longer crashes** writing the live report; tiny eval sets that would produce an empty train split now fail fast with guidance.
- **Eval viewer**: clicking OK after Submit no longer overwrites the completed feedback.json; auto-save status is honest in static mode; run sorting no longer crashes on mixed eval_id presence; embedded JSON escapes all `<` (covers `<!--`/`<script`, not just `</script>`); grader evidence is attribute-escaped.
- **`quick_validate.py`** rejects empty/whitespace name and description, and enforces name-matches-folder.
- **`package_skill.py`** excludes `tests/` from artifacts, skips symlinks instead of dereferencing them, and prints a friendly error when run as a plain script. The release workflow now builds through it, so exclusions apply to published zips.
- **Agent contracts**: grader copies timing.json verbatim (incl. `total_tokens` — real token counts now reach benchmarks); comparator declares its output path and counterbalances position bias; analyzer notes are merged into benchmark.json via the new `--notes` flag.
- **Docs**: packaging is unconditional (no longer gated on the Claude.ai-only `present_files` tool), static-mode feedback documentation matches viewer behavior, schemas.md documents all four configuration strings and eval_metadata.json, run_loop cwd requirement stated, license is a top-level frontmatter field, SKILL.md is back under 500 lines (environment + description-optimization details moved to references/).

### Added
- `aggregate_benchmark.py --notes <file>` merges analyst notes into benchmark.json.
- `tests/`: coverage for aggregate_benchmark, generate_report, run_eval scoring, run_loop split, package_skill planning, generate_review — and CI now runs the suite.
- `docs/DEVELOPMENT.md`: tracked developer reference (was only in the gitignored CLAUDE.md).

## [0.4.2] - 2026-04-27

### Fixed
- **`aggregate_benchmark.py`: warns when an eval directory has no `grading.json` in any config subdirectory.** Previously such evals were silently skipped — common when a grader run is interrupted partway through, leaving some evals graded and others not. The benchmark would then cover only the evals that finished, with no signal that data was missing. Now emits a single warning listing every skipped eval directory by name so partial-run silent data loss is visible.

## [0.4.1] - 2026-04-27

### Fixed
- **`aggregate_benchmark.py`: `runs_per_configuration` is now computed from data instead of hardcoded to `3`.** The metadata field claims a per-(eval, config) run count; previously `benchmark.md` always rendered "3 runs each per configuration" regardless of how many grading.json files actually existed. Now derives the value by counting runs per (eval_id, configuration) pair.
- **`aggregate_benchmark.py`: silent-zeroing of pass rates is now a loud warning.** When a `grading.json` is malformed or schema-divergent (e.g., missing the top-level `summary` object documented in [`references/schemas.md`](skill-creator-plus/skills/skill-creator-plus/references/schemas.md)), the script previously defaulted every metric to 0 with no signal. Now emits a clear warning to stderr identifying the file and the missing key, so users see the failure mode immediately instead of debugging mysterious 0% pass rates.

## [0.4.0] - 2026-04-27

### Added
- **Designing Scripts for Agent Use** — new section in `references/official-guide-patterns.md` covering the conventions that make a bundled script usable to an agent rather than just to a human: non-interactive, `--help`-documented, structured output (JSON/CSV), helpful error messages, meaningful exit codes, idempotency, dry-run support, predictable output size, and inline dependencies (PEP 723 etc.). Pointer added to SKILL.md.
- **Dual-purpose script framing** in SKILL.md: the same `validate_X.py`/`smoke_test_X.sh` users run can also serve as an eval-time grader assertion (and vice versa). Made explicit in both the grading step and the convergence-signal section.
- **Script-when / Instruct-when first-pass heuristic** in SKILL.md's draft-time design step, with an explicit note that the strongest signal still comes downstream from convergence in eval runs.
- **`scripts/requirements.txt`** declaring `pyyaml` so the validator's only non-stdlib dependency is documented.

### Changed
- **`quick_validate.py` is now agent-friendly.** Converted to argparse (was hand-rolled `sys.argv`), added `--json` mode (`{"valid": …, "error": …, "skill_path": …}`), graceful `ImportError` for missing PyYAML (exit 2 instead of traceback), and a `Path.exists()` pre-check that fires distinct exit code 3 for "skill directory not found" vs. 1 for validation failure. Exit codes are documented in `--help` epilog.
- **`package_skill.py` is now agent-friendly.** Converted to argparse, added `--dry-run` (lists files and target path without writing the zip), `--json` mode (structured output replacing emoji prose), and a stderr warning when overwriting an existing artifact. Exit codes documented in `--help` epilog.
- **Consistent `--help` epilogs** across all argparse-using scripts (`aggregate_benchmark`, `generate_report`, `improve_description`, `run_eval`, `run_loop`) — every script now documents its example invocation and exit-code semantics.

## [0.3.0] - 2026-04-21

### Added
- **Portable skill spec support.** `quick_validate.py` now accepts the full [agentskills.io](https://agentskills.io/specification) cross-host spec (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`) *plus* all documented Claude-specific fields (`when_to_use`, `model`, `effort`, `agent`, `paths`, `hooks`, `shell`, `context`, `disable-model-invocation`, `user-invocable`, `argument-hint`) *plus* undocumented-but-functional (`version`, `arguments`, `created_by`). Each field is type-checked; values outside documented ranges (e.g. `context` other than `'fork'`, bad `effort` keywords, non-boolean `disable-model-invocation`) are rejected with specific error messages.
- **Combined-length check.** Validator rejects `description + when_to_use > 1,536` characters — Claude Code v2.1.116 truncates skill-listing entries at that threshold, so catching it pre-flight prevents silent truncation at runtime.
- **First unit test file for the validator** (`tests/test_quick_validate.py`, 17 tests) covering field acceptance, type rejection, boundary cases, and the new combined-length check.
- **Portability-first docs.** SKILL.md frontmatter guidance now teaches the portable core first and flags Claude-specific fields as optional extensions. New "Runtime Mechanics & Gotchas (Claude Code)" section in `official-guide-patterns.md` documents the ~8 KB listing budget, ~20-char collapse threshold, 1,536-char per-entry truncation, chokidar depth-2 live-reload, gitignore-syntax `paths:` matching, and MCP skill carve-outs.
- **Listing-collapse troubleshooting entry** for the failure mode where every installed skill collapses to name-only when any skill's share of the listing budget drops below ~20 chars.
- **Description optimizer: `--target-length`** (default 500) — soft target surfaced to the improver. Selection uses length-aware tuple-keys so ties break toward the shortest description. Hard cap of 1,024 chars (agentskills.io spec) is preserved.
- **Description optimizer: `--plateau-patience`** (default 2) — stops the loop early if the test score hasn't improved in N consecutive iterations, instead of burning all iterations appending verbiage.
- **Per-attempt char counts** surfaced in the improver's history view, so the model can see the length-cost trajectory and prefer tighter rewrites.

### Changed
- Description optimizer prompt now explicitly frames the portability constraint (output must stand alone for hosts that only read `description`) and explains the Claude listing-budget collapse mode — so the improver stops drifting toward bloated 1,024-char descriptions.
- `run_loop` verbose output now includes the length trajectory of all attempted descriptions alongside the score trajectory.
- Selection tie-break: when test scores tie, the shorter description wins.

### Fixed
- Validator no longer rejects legitimate SKILL.md frontmatter. The previous allowlist was 10 fields; the new one is 19 (all portable spec + all documented Claude-specific + all undocumented-but-functional).

### Portability notes
- Optimizer still emits a single `description` field. It never splits into `description + when_to_use`, so output stays cross-host portable.
- `when_to_use` is supported but never recommended as the default — the portable pattern remains "everything in `description`."

## [0.2.1] - 2026-04-14

### Fixed
- `quick_validate.py` now accepts the four frontmatter fields documented in `official-guide-patterns.md` that it previously rejected as "unexpected": `disable-model-invocation`, `context`, `argument-hint`, and `user-invocable`. Skills using these fields can now be validated and packaged successfully.
- Added value validation for the newly-recognized fields: `context` must be `'fork'`; `disable-model-invocation` and `user-invocable` must be booleans; `argument-hint` must be a string under 200 characters.

## [0.2.0] - 2026-04-06

### Added
- "Script vs. Instruct" decision framework in `official-guide-patterns.md` — when to offload work to bundled scripts vs. keep as SKILL.md instructions, with concrete examples and a decision walkthrough.
- Expanded "Store Scripts & Let Claude Compose" section with restored Thariq example and "Why Offload to Scripts" rationale (context window efficiency, reliability, speed, auditability).
- Brief "Script vs. Instruct" pointer in SKILL.md design phase so guidance surfaces at the right workflow moment.
- Cross-reference from the improve phase's "repeated work" observation to the new decision framework.

## [0.1.5] - 2026-04-02

### Fixed
- Eval viewer "Submit All Reviews" no longer causes a blank white page in Cowork. The blob URL download (`a.click()`) navigated Cowork's embedded viewer instead of downloading. Removed the download attempt in static mode — the copyable JSON textarea is the reliable feedback path.

## [0.1.4] - 2026-04-02

### Fixed
- `aggregate_benchmark.py` now accepts descriptively-named eval directories (e.g., `auto-fit-headlines/`), not just `eval-*`. The SKILL.md says to use descriptive names but the script's glob didn't match them.
- `package_skill.py` defaults output to the skill's parent directory instead of `Path.cwd()`, which is read-only in Cowork.

## [0.1.3] - 2026-04-02

### Fixed
- Eval viewer crashes when skill outputs contain HTML with `</script>` tags. The embedded JSON now escapes `</` to `<\/` before injection into the `<script>` block, preventing the browser from prematurely closing it.

## [0.1.2] - 2026-04-02

### Fixed
- Eval viewer static mode (Cowork) now reliably shows the copyable JSON textarea. Previously, `showDoneDialog()` relied on `fetch("/api/feedback")` failing to detect static mode, but in Cowork the fetch doesn't fail because the HTML is served through Cowork's infrastructure. Now `generate_review.py` injects an `is_static` flag into the embedded data, and the JavaScript checks that flag directly.

## [0.1.1] - 2026-04-02

### Fixed
- `aggregate_benchmark.py` silently produced empty results because it required undocumented `run-*/` subdirectories inside config dirs. The script now reads `grading.json` directly from config directories (e.g., `eval-1/with_skill/grading.json`), matching the layout described in SKILL.md.
- SKILL.md now explicitly states where to save `grading.json` (in each config directory).
- Cowork eval viewer feedback guidance rewritten to explain the *why* instead of using all-caps directives.

## [0.1.0] - 2026-04-01

### Added
- Initial open-source release
- Skill creation workflow with intent capture, success criteria, and iterative improvement
- Evaluation system: parallel with-skill and baseline runs, assertion grading
- Benchmarking with mean/stddev aggregation and delta comparison
- Blind A/B comparison via comparator and analyzer agents
- Description optimization loop with train/test split to prevent overfitting
- Interactive eval viewer (browser-based and static HTML modes)
- Skill validation and packaging scripts
- Three specialized agents: grader, comparator, analyzer
- Reference guides: official Anthropic patterns, JSON schemas
- Support for Claude Code, Claude.ai, and Cowork environments
