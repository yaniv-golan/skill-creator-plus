# Changelog

All notable changes to this project will be documented in this file.

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
