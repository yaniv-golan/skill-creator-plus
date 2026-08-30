# Changelog

All notable changes to this project will be documented in this file.

## [0.11.0] - 2026-08-30

Two shipped mechanisms were measured and found not to work: the trigger eval could not measure a
skill that was also installed, and the skill's own script-path guidance was unreachable at the
moment it was needed. Both were found by running the thing rather than reading it, and both fixes
carry a negative control — the guard was deliberately broken and confirmed to fail.

### Fixed
- **The trigger eval could not measure a skill that was also installed.** `run_eval` synthesizes a
  uniquely-named copy, but `claude -p` also sees every plugin under `~/.claude`. When the skill under
  test is one of them the model reaches for the *real* one, and the detector — matching the synthetic
  name — correctly scores that as "did not trigger". Measured on this repo's own skill: **8/24, with
  all 16 positives failing**, including a query the description names almost verbatim. That is the
  advertised "optimize my skill description" capability returning noise in its likeliest use. Now:
  `HOME` is isolated when a credential is in the environment, a canary proves the detector can fire
  before any score is reported, and a run that invoked an installed skill is refused rather than
  scored. `isolated` and `canary` ride in the output JSON, so a regression is visible in every
  artifact rather than only in CI. Exit **4** distinguishes "measured nothing" from "scored badly" —
  conflating them would let the optimizer tune against noise.
- **The script-path guidance never reached the user asking for it.** A harness probe of the exact
  question — *how does a SKILL.md run its bundled script* — showed the skill was not selected on
  Sonnet, which answered from priors with a bare relative path plus a **fabricated** resolution
  mechanism this skill's own reference contradicts. The description now puts single narrow mechanics
  questions in scope, and the answer is in the always-loaded body rather than behind a
  cross-reference. Verified after the change at both model tiers.
- **`${CLAUDE_PLUGIN_ROOT}` in a shell is not merely empty — it can be set and wrong.** A plugin's
  `Setup`/`SessionStart`/`CwdChanged`/`FileChanged` hook can export its environment through
  `CLAUDE_ENV_FILE`, so an unrelated plugin's root lands in the session env and every later Bash call
  inherits it. Checking whether it is empty therefore returns clean on the real failure. Inspect
  `~/.claude/session-env/<session-id>/` to see whose exports are in your shell.
- **The compaction rule flagged files the runtime never truncates.** Truncation fires at 20,002
  characters (`Math.round(len/4) > 5000`, half-up), while 19,900 is what *survives* it. Gating on the
  survivor flagged a 101-character band for a truncation that never happens.

### Added
- **`compaction-zeroing-risk`**, a plugin-level lint rule. Over the 25,000-token combined cap a skill
  is not truncated but **zeroed** — written back as the empty string, with no marker and no entry —
  and stays dropped for the session. Truncation announces itself; this does not, so authoring time is
  the only place it is detectable.
- **`assets/skill-script-invocation.md` and `assets/plugin-bin-launcher.sh`** — paste-in wording for
  how an authored skill reaches its own scripts, and a `bin/` launcher template. Both are tested by
  committed harness scenarios built *from* them. Building a fixture out of the templates and running
  it surfaced three defects that two review passes had missed — a launcher pointed at the wrong
  script directory, an error path silenced by `set -euo pipefail`, and a fallback tier that does not
  exist in the lane it was written for. Only the third was found *by* the harness; the first two were
  found by exercising a fixture the harness had required be committed before it would stage it.
- **Harness fixture and scenarios for the shipped templates**, plus a guard on the skill's own
  script-path answer.

### Changed
- **Path Variables is reframed as load-time substitution, answer first.** These are not runtime
  variables; nothing exports them. The per-token liveness table is now fully measured, including the
  trap that the answer is **token-specific, not surface-specific**: a `commands/*.md` substitutes
  `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_PROJECT_DIR}` and
  `${CLAUDE_SESSION_ID}` but **not** `${CLAUDE_SKILL_DIR}`. Asking "does substitution happen in
  commands?" returns a truthful yes and sends you the wrong way.
- **The `bin/`-on-PATH pattern is an optimisation, not a fallback.** Measured: the plugin `bin/` is on
  PATH at `container` and `microvm` — the lanes where the read path already works — and absent at
  `hostloop`, the one lane with the namespace split it exists to bridge. The stanza therefore ranks
  the path-as-read first and a filesystem search second.
- **`README.md` corrected where it had gone stale**, not extended: the runtime-docs claims now cite
  2.1.251 rather than 2.1.222, and the compaction description says what is actually enforced — a
  CHARACTER gate, and *two* ways to lose content, since it previously described only truncation and
  not the combined cap that zeroes a skill outright.
- **cowork-harness floor raised to 3.0.0**, which renames `l0_plugin_divergence` to
  `l0_host_config_contamination` and adds `allow_host_hooks`. The loader is a `strictObject`, so an
  older CLI hard-errors rather than ignoring a new key.

## [0.10.0] - 2026-08-28

Path guidance under Cowork was wrong in four places, and one of them re-created the exact failure it was written to prevent. Every claim below was re-verified first-party against Claude Code 2.1.247.

### Fixed
- **The workspace instruction told agents to hide the workspace.** `references/environments.md` said to put it "under the outputs directory" — but in Cowork the agent's working directory already *is* that directory, so `outputs/<name>-workspace/` resolves to `outputs/outputs/…` and stops appearing in the user's Working-folder panel. The write succeeds and the tool reports success, so nothing fails loudly. It also said a connected folder could be named relatively; only an absolute path reaches one, and a relative name silently creates a decoy directory inside outputs instead.
- **The eval loop wrote its own results where nobody could reach them.** Seven shell commands in `SKILL.md` passed relative `<workspace>/…` paths — the benchmark, the analyst notes, the viewer and its PID file. Under Cowork the shell starts in the session root, not the outputs directory, so those resolved into VM-private space. The `viewer.pid` round-trip was doubly broken: shell calls carry no working directory between them, so `cd`-then-use-relative cannot work either. Paths are now resolved once and passed absolute.
- **The eval dispatch prompts sent sub-agents relative paths, so the analyst notes and both baseline output sets were misplaced too.** Four paths in the Step 1 block — `outputs/user_notes.md`, `outputs/metrics.json`, `without_skill/outputs/` and `old_skill/outputs/` — went verbatim to sub-agents whose file-tool working directory already *is* the outputs directory, so each doubled and landed outside the eval run directory it was meant for. Separate from the shell-command fix above: these are file-tool paths, and two of them were invisible to every lint rule considered. All four now carry the explicit absolute placeholder, not a back-reference like "that same directory" — a sub-agent receives this text with no author present to disambiguate.
- **`SKILL.md`'s packaging step said "never to cwd"**, which in Cowork steers away from the only user-visible location there is.
- **`package_skill.py`'s default output directory is unwritable where most installs put the skill.** It defaults to the skill folder's parent, which on a plugin or marketplace install is a read-only cache — the same read-only mount the workspace rule already warns about, reached by a different route. The guidance now says so and tells you to pass the destination explicitly, absolute when a script will consume it.
- **`--static` asked for a path without saying which kind.** Both `SKILL.md` and `references/environments.md` now ask for an absolute one, and `generate_review.py` prints the **resolved** path it wrote rather than echoing the argument back. That makes a misrouted write visible; it does not make it correct.
- **`run_loop.py --report` defaulted to the system temp directory** whenever `--results-dir` was given, and `references/description-optimization.md` instructed a `/tmp` write followed by `open`. Both are unreachable under a sandboxed runtime. The report now lands beside `--results-dir` when there is one (temp remains the fallback when there isn't), and the anchor directory is created before the first write.
- **`official-guide-patterns.md` stated two conditional compaction behaviours as unconditional.** Truncation write-back and combined-cap zeroing are both skipped when a skill's content is already in the conversation body, and a skill carried as an attachment is not re-attached, truncated or zeroed at all. The same overstatement was in `compaction-truncation-risk`'s message.

### Added
- **A one-pass path, for when the user wants the skill rather than an eval report.** The document was organised entirely around the eval loop, and the only sanction for skipping it was a throwaway line naming no substitute verification — so on the modal request ("give me the finished skill") the agent walked off the documented map and improvised. There is now a named route: draft → smoke-test every bundled script on synthetic input with the problems planted → `quick_validate` + `check_portability` → package → deliver → *then offer* evals. It says plainly that those two steps **are** the verification when evals are skipped: shipping without eval evidence is fine, shipping with nothing exercised is not.
- **The authored skill directory now has a stated home, addressed per tool family — and a rule never to delete from outputs.** The workspace, the evals directory and the `.skill` output all had a stated location; the skill being created did not, so it was placed by guesswork. "Your working directory" is not one place: authoring is mostly shell work and the shell's cwd is not the file tools', so the rule now names both forms and says to build in one place rather than keeping a second copy to sync. Related and previously unstated anywhere: **production denies `unlink`/`rmdir` under outputs** until the user approves, so a "remove the stale copy and re-copy" step fails there while succeeding in most test setups.
- **The three dispatched sub-agents are told their paths arrive resolved.** `agents/grader.md`, `agents/comparator.md` and `agents/analyzer.md` now say that every path parameter is absolute, to use it exactly as given, and not to write anything relative to "here" — a sub-agent has no author present to disambiguate, and the shell's working directory is not the file tools'. `comparator.md`'s old fallback ("save to `comparison.json` in the current working directory") is replaced with a defined location and a requirement to state the full path it wrote.
- **A truncation-recovery instruction**, in the part of `SKILL.md` that survives truncation: if a section this file refers to appears to be missing, it was cut — re-read from disk before continuing. Scoped to the case it can actually detect, since the marker is in-band for truncation but a skill dropped whole by the combined cap leaves no signal at all.
- **An optional SKILL.md body skeleton** in `references/official-guide-patterns.md` (Workflow / Options / Interpretation / Gotchas / Adjacent inputs), explicitly non-normative — improvising an order is the anti-railroading posture, not a defect, but starting from nothing costs time.
- **The bash-vs-file-tool path split, stated for the first time.** `Read`/`Write`/`Edit` start in the outputs directory; the shell starts in the session root, and anything outside `/sessions/<id>/mnt/` — `/tmp` included — reaches neither the user nor the file tools. No relative path is correct for both families, so bundled scripts take absolute paths. Also documented: shell calls carry no cwd between them; a sub-agent cannot resolve a connected folder's mount name from its own prompt, so a dispatching skill must pass the resolved path; and `Write`'s result echoes the path it was *given*, not a resolved one.
- **`outputs-prefix-relative` lint rule** (warning, Cowork-only). Flags a workspace placed under a relative `outputs/` path. Deliberately narrow — it matches only paths resolving to a `-workspace` directory, because a wider rule has to guess what base a bare `outputs/` is relative to, and guessing is how a rule ends up firing on correct text.
- **Two script-authoring conventions** in `official-guide-patterns.md`: accept absolute output paths and echo back the resolved one, and phrase a sandbox path as the shell's location or a script's argument rather than as a file-tool write target — the latter is a real denial, and static checkers flag it.
- **An authoring principle: declare at authoring time, probe at run time, never detect the host.** `--target` states where a skill is meant to run; at run time a skill branches on whether the capability it needs is present, never on which product it thinks it is in — which is what the delivery rule already did by naming no tool and no runtime. Documents why an environment marker like `CLAUDE_CODE_IS_COWORK` is the trap: a skill spans two execution contexts and the shell context is sealed, so the check reports "not Cowork" in precisely the configuration that needed detecting. For paths the rule is stronger — probe for nothing: the caller resolves once and passes an absolute path, and a standalone script takes the destination as a required argument and fails loudly rather than inventing a directory.
- **What to do instead of one shared path string.** The guidance stated the prohibition ("no single path form is correct for both families") without the remedy. Now: keep the identifier and the base apart — name a run or workspace as a bare fragment carrying no prefix, and let each family supply its own base at the point of use. One directory, two spellings; the shared *string* is what cannot be made correct, not the shared directory.
- **A committed cassette for the negative control, so over-triggering is gated on every PR.** `no-trigger` asserts that an unrelated prompt does *not* invoke the skill — a live risk every time the `description` changes, which this release did. It is the one scenario worth committing: cheap, no binary artifact, and `no_skill_triggered` is content-class so it survives replay. CI already replayed any cassette it found, so this needed no workflow change. The other two stay live-only — they bake an un-scannable `.skill` zip into the recording and go stale on nearly every skill edit.
- **A known-coverage-gap note in `harness/README.md`.** No harness tier reproduces the cwd split, so a green dogfood does not certify script output paths. `containedPath` prevents a stray write from satisfying `file_exists`, `user_visible_artifact` or `computer_links_resolve`; the exposure is `semantic_matches`, which is what `remote-delivery.yaml` grades on. Also records two probe-method traps: `audit.jsonl` rewrites VM paths and will corrupt a path comparison, and a model may silently prepend `cd` to the command under test.

### Changed
- **The Claude-specific frontmatter mechanism moved out of `SKILL.md` into `references/official-guide-patterns.md`.** `when_to_use`, `allowed-tools`, `disallowed-tools` and `shell` keep their *rules* in `SKILL.md`; the explanation behind them — that `allowed-tools` grants rather than prompts, that the real gate is workspace trust accepted once per folder, and that Cowork shows `when_to_use` in only one of two listings — now lives in the reference. If you went to `SKILL.md` for the workspace-trust explanation, it is one file over. This is the compaction budget doing its job: rules in the capped file, mechanism in the uncapped one.
- **The SKILL.md size rule now states the metric that actually binds: characters, not lines.** The guidance led with "keep it under 500 lines" — a heuristic that cannot protect a character budget, and this repo was its own counterexample: 496 lines (passing the rule it teaches) at 2.07x the limit it documented in its own lint rule. Every skill authored with the tool inherited the wrong metric, and the packaging checklist repeated it. Now `wc -m` against 19,900 characters, with the line count dropped rather than demoted.
- **The post-compaction cap is re-verified at 19,900 characters and now documented as derived arithmetic.** The value is unchanged; what changed is that it is no longer presented as a literal you could grep for. It is `5,000 tokens × 4` minus a 100-character truncation marker — 98 visible characters plus two leading newlines, a detail that makes the marker easy to mis-measure as 98 and the cap as 19,902. The 5,000 and 25,000 constants are unchanged across 2.1.222, 2.1.246 and 2.1.247: three builds, three minified namings, identical values.
- **The chars-per-token divisor is documented as derived, not binary-verified.** *(Superseded in 0.11.0: the size function was located — `Math.round(e.length/t)` with `t=4` — so the budget is literally a character gate.)* The truncator's `× 4` implies the model, but the size function itself could not be resolved. The character budget, which is what the linter gates on, is unaffected.
- **The combined 25,000-token budget is consumed by post-truncation sizes**, so a large skill contributes its capped 5,000 tokens rather than its full length. Read with the most-recently-invoked-first ordering, this explains a counter-intuitive outcome: the skill that vanishes is rarely the big one.
- **`references/environments.md` no longer identifies the session scratchpad as `CLAUDE_CODE_TMPDIR` / `CLAUDE_TMPDIR`.** That variable is real — a per-uid temp-directory override defaulting to `/tmp` — but it is not the scratchpad. The guidance is now stated by outcome: a deliverable goes to a bare filename or an absolute outputs path, and anywhere else is a temporary file by definition.
- **`harness/README.md` now states what replay does not cover.** Guards (`outputs-delete`, `host-path`) run off the live run's scan, which a cassette does not carry — a replay reports them as `—`, not as passing. The one real bug this suite has caught was a guard rather than an assertion, so a replay would have shown eight green asserts and missed it. The replay lane is regression cover for content, never a substitute for a live run.
- **The "relative `outputs/…` path" hazard is documented in `references/environments.md`.** A path whose first segment is `outputs/` resolves against whichever cwd the reading tool has — doubling for a file tool, landing in VM-private scratch under the shell — and both writes report success. It is taught as prose rather than enforced by a lint rule: the hazard depends on a base the text does not state, and a rule for it flags correct explanations of the bug about as often as the bug.
- **Shell working-directory carryover is measured, not assumed, and it is lane-dependent.** A two-call `cd`/`pwd` probe (`harness/scenarios/shell-cwd-carryover.yaml`) returns the `cd`-ed directory at VM-loop fidelity and the unchanged session root at host-loop — using a different shell tool in each case. So a claim sourced from host-loop artifacts and shipped unscoped was false on the other lane. The guidance says carryover is *unreliable* rather than absent, and the operative rule — resolve once, pass absolute — is correct on both tiers and needs no lane knowledge. Both runs also put the shell's base at `/sessions/<id>`, previously an inference. The scenario carries its own measured answer so the result need not be re-purchased.
- **One assumption is now stated rather than left silent.** The path guidance describes Cowork's default configuration, where only the shell is sandboxed. Locked-down orgs can run the whole agent inside the sandbox, where the file tools appear to start at the session root — which would make a bare filename invisible for them too. Inferred from the sandboxed agent's own working directory and not observed here, so the instruction is unchanged and the assumption is marked with a debugging pointer.
- **[cowork-harness](https://github.com/yaniv-golan/cowork-harness) pin 1.19.0 → 2.4.0** across CI, `docs/DEVELOPMENT.md`, `harness/README.md` and the shipped `references/environments.md`. The floor now carries the `fidelity:` default warning, which matters for authored skills: a scenario omitting `fidelity:` is silently measured against the VM-loop lane rather than the host-loop one production uses.
- **The dogfood's coverage-gap note names the current reason.** It said the gap was blocked on upstream work; that work shipped in cowork-harness 2.4.0. The gap remains because every scenario here is `fidelity: container` while the tier reproducing production's path split is `hostloop` — closing it means adding a hostloop scenario, which is a real decision rather than a config change.
- **The Cowork section no longer inherits the Claude.ai section's `/tmp` staging steps.**

## [0.9.0] - 2026-08-06

Every Claude-runtime claim in this repo was re-verified against the shipping Claude Code binary. Four were wrong and are corrected below.

### Added
- **`compaction-truncation-risk` lint rule.** Flags a `SKILL.md` over the 19,900-character limit that survives auto-compaction, and names the line where the cut falls. The cap is a fixed character count in the runtime, so the check is exact rather than a heuristic. Advisory severity.
- **Compaction-budget guidance in `references/official-guide-patterns.md`.** The per-skill cap is documented as "5,000 tokens" but enforced as **19,900 characters** (100,000 combined across skills), because the runtime sizes skill content by character count rather than tokenizing it. Measure with `wc -m`. Also documents two behaviours that are easy to lose content to: truncation is written back, so a second compaction cannot recover the tail, and combined-cap overflow drops a skill's content entirely for the rest of the session.
- **Cowork shows a skill listing twice, and only one copy carries `when_to_use`** — a second reason never to put trigger-critical content there. Cowork and cloud sessions also load skills from your claude.ai account rather than `~/.claude/skills/`, so local edits are not what runs.
- **Skill content lifecycle**: an invoked `SKILL.md` enters the conversation once and persists for the session, while the `allowed-tools` grant clears on the next user message. Plus `background: false` with `context: fork` (Claude Code 2.1.218+).

### Changed
- **Advisory findings no longer gate `check_portability.py --strict`.** Warnings and errors gate exactly as before; `--strict-advisories` restores the old behaviour. Without this, the `thirdparty-import` change below could not take effect.
- **`thirdparty-import` no longer fires on Cowork's preinstalled Python stack.** numpy, pandas, requests, PyYAML, bs4, openpyxl, Pillow, matplotlib, python-docx and python-pptx are present in the image and installing from PyPI works, so the rule was a false positive on the most common case. Those ten import roots are now silent; anything outside them is advisory, noting per-run install cost and that egress is org-configurable.
- **`device_commit_files` is documented rather than banned.** Surfacing a file in the conversation and writing it onto the user's device are different outcomes, and only the first is what "present it" covers. Skill text should still describe the outcome and name no tool.
- **Runtime documentation re-pinned to Claude Code 2.1.222**, and stale model IDs in three `--help` epilogs, `references/schemas.md` and `harness/sessions/skill.yaml` refreshed to `claude-opus-5`.
- **[cowork-harness](https://github.com/yaniv-golan/cowork-harness) pin 1.16.0 → 1.19.0**, with the CI lint step now running `--strict --min-severity WARN` (without both flags it cannot fail on a WARN-class rule).

### Fixed
- **The generated skill was written where the user cannot see it, and on remote Cowork destroyed.** `SKILL.md` placed the working directory beside the skill directory, which is a read-only cache on plugin and marketplace installs; the agent then fell back to a session scratchpad that a remote session discards on exit, taking the new skill, its scripts and every eval result with it. It now requires a user-visible, writable location.
- **The eval viewer was never shut down.** `VIEWER_PID=$!` and `kill $VIEWER_PID` sat in separate shell invocations, so the variable was unset by the time it was read and the server kept running. The PID is now written to a file.
- **Listing overflow degrades per skill, not all at once.** There is no ~20-character collapse threshold: Claude ranks skills by recency-weighted usage and drops whole descriptions starting with the least recently used, so full and name-only entries coexist. A large description mostly costs itself. The `listing-collapse-risk` rule is renamed **`listing-desc-drop-risk`** — **update any tooling that keys on the old name.**
- **The listing budget is not a fixed ~8 KB.** It is `contextWindow × 4 × skillListingBudgetFraction` (default `0.01`), so a 1 M-context model gets ~40,000 characters. The 1,536-character per-entry cap is the `skillListingMaxDescChars` default rather than a constant. Also documents `skillOverrides` and the `/doctor`, `/skills` and `/context` diagnostics.
- **`allowed-tools` grants permission; it does not request it.** No permission prompt is triggered by populating `allowed-tools`, `hooks` or `shell`. It pre-approves tools for the invoking turn, clearing on the next user message, and the real gate is workspace trust, accepted once per folder. `disallowed-tools` is the denylist and is now documented as a skill field. Adds the MCP-sourced and shared-memory carve-outs where this frontmatter is ignored.
- **"In Cowork, cwd is a scratchpad the user can't see" is withdrawn.** cwd is the outputs mount. The instruction it justified — write to a stated path, then present it — is unchanged and still correct.
- **The Cowork eval-viewer step no longer contradicts the delivery rule** by suggesting a bare link, which cannot work on the remote lane.

## [0.8.0] - 2026-08-01

### Added
- **Delivery guidance for skills that produce a file for their user** — a new *Delivering Files the Skill Produces* section in `SKILL.md` (plus a checklist item), expanded in `references/environments.md` → *Delivering files to the user*. Two ordered steps, phrased by outcome and naming no tool: **(1)** write the deliverable to a stated path, unconditionally, and never to cwd — in Cowork, cwd is a scratchpad the user can't see; **(2)** then scan your available tools for one whose description says it sends or presents files to the user, and **call it if one exists** — stating the path is not a substitute. Only if none exists, state the path. This matters because Cowork's two lanes deliver differently: on the local lane the write plus a stated path completes delivery, but on remote cloud-container Cowork the session runs in a sandbox destroyed when the session ends, so a file that is written and never presented is **silently lost**. The guidance is unconditional on the author's own environment — the risk lives in the runtime the *authored* skill will run under. `present_files` and `SendUserFile` appear only as a recognition aid for reading a transcript, never as text to copy into an authored skill; `device_commit_files` is never named at all. Sources are limited to publicly checkable ones: `anthropics/claude-code` issues #50041, #76344, #36438, and Anthropic's Cowork architecture overview.
- **Two `check_portability.py` rules** (both warning). `delivery-tool-single-lane` fires when a skill names one delivery-tool family (`present_files` or `SendUserFile`) anywhere in its text but not the other, stranding the Cowork lane served by the missing one — phrasing delivery by outcome and naming neither is the recommended pattern and stays clean, as does naming both. `delivery-conditional-deliverable` fires when a clause gates *production* of the artifact on a delivery tool's availability (a skip/omit phrase plus a production verb), which is the real upstream failure mode; legitimate capability-conditional *presentation* is not flagged. Both are suppressed per-file by a `portability-allow: file-delivery-tool` marker in comment context. A self-lint test pins this skill's own wording against both rules.
- **Two harness scenarios exercise the delivery guidance above at runtime, one per Cowork lane.** `harness/scenarios/create-skill.yaml` (local lane) now asserts `present_files_called: true` — hard, evidence-backed proof the packaged file was actually surfaced, not just written. `harness/scenarios/remote-delivery.yaml` (new; remote lane, where `user_visible_artifact` and `present_files_called` are rejected at load time because no delivery tool exists there and the harness's transcript can't see tool calls at all) instead grades via `semantic_matches` whether the deliverable was written to an explicitly stated, user-reachable location and that location was communicated — the observable, lane-appropriate signal. Both are live-only and never a PR gate; CI load-checks them. Neither assertion has yet been observed passing on a live run — both are marked as such inline, so a first red is investigated rather than assumed to be a regression.
- **A token-free scenario load gate in CI** (`cowork-harness record harness/scenarios/ --dry-run --quiet`). `lint` only warns on an unknown key, so a scenario that lints clean can still fail to load — a green lint is not evidence the suite runs.

### Changed
- **[cowork-harness](https://github.com/yaniv-golan/cowork-harness) pin 1.2.0 → 1.16.0** across CI, `docs/DEVELOPMENT.md`, `harness/README.md`, and the shipped `references/environments.md` (which still advertised a 1.1.0 floor to every installed agent). `lane:` requires ≥ 1.14.0.

### Fixed
- **The packaging step no longer names a file-delivery tool, or attributes one to the wrong surface.** `SKILL.md` told authors to present the packaged `.skill` via `present_files` "(Claude.ai)" — a hardcoded tool name plus an unsupported attribution; no public evidence indicates Claude.ai chat serves `present_files`, and the only confirmed server of it is Cowork's desktop-local lane, where it is MCP-namespaced as `mcp__cowork__present_files`. The step now follows the delivery guidance above and names no tool. The `[0.5.0]` entry below repeats the same misattribution and is left as shipped, since released entries are a historical record.

## [0.7.0] - 2026-07-16

### Fixed
- **`quick_validate.py` / `package_skill.py` no longer require PyYAML at runtime.** They imported PyYAML, which Cowork's container image lacks and its default-deny egress can't `pip install` — so both crashed (or the agent fell back to hand-validation) when the skill ran under Cowork. Replaced with a stdlib-only `scripts/frontmatter.py` parser covering the frontmatter YAML subset (scalars, nested mappings, block/flow sequences, block scalars) and rejecting exotic constructs (anchors/aliases/tags/merge/multi-doc) with a clear error. Behavior is identical across runtimes because there's a single parser; a differential test (`tests/test_frontmatter.py`) keeps it aligned with `yaml.safe_load`. PyYAML is now a test-only dependency. quick_validate exit code `2` is retired to "reserved".

### Added
- **`scripts/check_portability.py`** — a stdlib-only cross-runtime portability linter. Flags constructs that break on a skill's target runtime: over-cap `description`, subagent use (absent on Claude.ai), `claude` CLI use (absent on Claude.ai), browser/server assumptions (no display in Cowork/Claude.ai), and third-party Python imports in bundled scripts (Cowork's sandbox lacks them and can't `pip install`). `--target claude-code|claude-ai|cowork|all`, `--json`, `--strict`.
- **`harness/`** — a [cowork-harness](https://github.com/yaniv-golan/cowork-harness) dogfood suite that regression-tests this skill under Claude Cowork's runtime, plus a token-free CI lane (`.github/workflows/harness.yml`).

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
