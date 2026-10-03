# Skill Creator Plus — Development Reference

## Quick Commands

```bash
# Validate skill structure
python skill-creator-plus/skills/skill-creator-plus/scripts/quick_validate.py skill-creator-plus/skills/skill-creator-plus
# JSON output for tooling: add --json. Exit codes: 0 valid, 1 invalid, 2 reserved (stdlib-only now), 3 path not found.

# Cross-runtime portability lint (stdlib-only; --target claude-code|claude-ai|cowork|all)
cd skill-creator-plus/skills/skill-creator-plus && python -m scripts.check_portability . --target all
# Rules: desc-over-hard-cap, listing-entry-truncation, listing-desc-drop-risk, subagent-dependency,
# claude-cli-dependency, browser-display-dependency, outputs-prefix-relative (cowork target only:
# a workspace under a relative `outputs/` path: refused on Desktop 2.7032.0+, nested and hidden on older
# Desktop, lost in a cloud session),
# relative-output-path (ADVISORY, claude-ai + cowork: SKILL.md or references/ tells the model to
# write a file to a bare relative path — invisible in a cloud session, refused by a local session's
# file tools, outside the outputs dir on the chat runtime. Precision over recall: imperative write verb +
# relative file path only; silent on absolute/~/$VAR/<placeholder> bases, bundled files, a basename
# the file anchors elsewhere, a stated base on the line, cd-to-absolute fences, and any line
# outputs-prefix-relative already owns. Suppress per file with
# `<!-- portability-allow: relative-output-path -->`),
# thirdparty-import (allowlisted against the local session's
# preinstalled stack), delivery-tool-single-lane, delivery-conditional-deliverable,
# plugin-bin-directory (PLUGIN-level, claude-ai-only: the plugin root — the dir holding
# `.claude-plugin/plugin.json` — has a non-empty `bin/`, which claude.ai rejects OUTRIGHT from
# organization distribution, by marketplace sync and by direct upload alike. LANE-SPECIFIC, not a
# deprecation: a top-level bin/ is correct and useful for a GitHub/local-CLI plugin, which is why
# it is a warning on one target rather than an error. Worth a rule because NOTHING ELSE LOCAL
# CATCHES IT — `claude plugin validate`, even --strict, passes a plugin carrying one (measured,
# 2.1.252), and the Desktop-side error is the generic "Marketplace sync failed. Check the
# repository URL and try again", with the real message only in the renderer log
# ~/Library/Logs/Claude/claude.ai-web.log. Does not fire on a standalone skill, on a bin/ inside
# the skill, on a bin/ above the plugin root in a marketplace repo, or on an empty one),
# compaction-truncation-risk (SKILL.md large enough to be truncated on re-attachment. TWO
# constants, 102 chars apart, and conflating them is a 101-char false-positive band: truncation
# FIRES at 20,002 chars (the runtime returns early while Math.round(len/4) <= 5,000, and JS
# Math.round is half-up), while what SURVIVES is 19,900 (5,000 x 4 minus a 100-char marker: 98
# visible chars + two leading newlines). Gate on the trigger, report against the survivor.
# Neither number is a literal in the bundle — both are derived from constants that are, and the
# derivation is now complete end to end: the size function resolves to
# `$c(e,t=4){...return Math.round(e.length/t)}`, so the budget is LITERALLY a character gate and
# `wc -m` has zero conversion error. The 5,000/25,000 caps are binary-verified across
# 2.1.222/246/247/251).
# compaction-zeroing-risk (PLUGIN-level, needs >=2 skills: the sum of post-truncation costs over
# `skills/*/SKILL.md` exceeds the 25,000-token COMBINED cap, so if one session invokes them all and
# then compacts, at least one is dropped WHOLE — written back as the empty string and omitted, with
# no marker and no entry. Truncation announces itself; this does not, which is why it is worth a
# lint rule: a running session cannot detect or recover from it, so author time is the only place
# it is visible. Post-truncation costs, so any single skill contributes at most 5,000 — 26 small
# skills trip it as readily as 6 large ones, and eviction is least-recently-invoked-first, so the
# one that vanishes is rarely the largest. Deliberately a LOWER BOUND: the runtime's budget spans
# every skill invoked in the session across all enabled plugins, not one plugin's. Reached by
# walking up from the linted skill to `.claude-plugin/plugin.json`; a standalone or single-skill
# plugin never fires it, which is why this repo's own baseline does not include it).
# --strict gates on warnings/errors only; advisories report but never gate (add --strict-advisories
# to gate on those too). Exit codes: 0 no gating findings, 1 gated, 2 usage error, 3 path not found.
# NOTE: CI does NOT run check_portability — `.github/workflows/validate.yml` runs
# quick_validate + unittest only. What actually guards this baseline in CI is the
# SelfLintTests in tests/test_check_portability.py, which lint the shipped tree. Don't
# read a green CI as the CLI having gated these rules. Two of those tests enforce what
# this comment claims: one asserts the finding-id SET is exactly the three below (so a NEW
# rule id reds CI rather than silently changing the baseline), and one asserts the
# whole SKILL.md fits its compaction cap (<= 19,300 with a load-time margin; 18,500 target)
# and that the load-bearing workspace, routing and running-evals-gate phrases are in it.
# Note this skill's own baseline: 3 findings (subagent / claude-CLI / browser deps, all Claude-Code-
# first by design; compaction-truncation-risk left in 0.17.0, when SKILL.md was cut under the cap) —
# so `--target all` is exit 0,
# and `--target cowork --strict` is exit 1 on the browser-display warning. A NEW rule id is the
# regression signal, not a non-empty finding list.

# Syntax-check all scripts
for f in skill-creator-plus/skills/skill-creator-plus/scripts/*.py; do python -c "import py_compile; py_compile.compile('$f', doraise=True)"; done

# Scripts are stdlib-only at runtime. PyYAML is a TEST-only dep (ground truth for the frontmatter
# differential test); install it to run the test suite:
pip install -r skill-creator-plus/skills/skill-creator-plus/scripts/requirements.txt

# Bump version (propagates to plugin.json + SKILL.md frontmatter)
./tools/bump-version.sh X.Y.Z

# Package skill as .skill zip (must run as a module — script uses package imports)
cd skill-creator-plus/skills/skill-creator-plus && python -m scripts.package_skill .
# Preview without writing: add --dry-run. Structured output: add --json.

# Run the test suite
cd skill-creator-plus/skills/skill-creator-plus && python -m unittest discover -s tests -v

# Merge analyst notes into a benchmark result
python -m scripts.aggregate_benchmark <dir> --notes notes.json  # merge analyst notes

# Trigger eval / description optimizer. EXPORT A CREDENTIAL FIRST — with ANTHROPIC_API_KEY,
# CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_AUTH_TOKEN in the environment, run_eval isolates HOME so the
# `claude -p` children cannot see your installed plugins. Without one it runs against your real
# ~/.claude, and a skill you have INSTALLED under the name being tested may answer instead of the
# synthesized copy — the detector scores that as "did not trigger" and the whole eval reads as a bad
# description. The run refuses rather than scoring when it detects this, but isolation avoids it.
# Check `isolated` and `canary` in the output JSON; exit 4 means INSTRUMENT FAILURE (nothing was
# measured), which is a different fact from a low score and must not be treated as one.

# cowork-harness static checks on the shipped skill (token-free, no Docker; needs cowork-harness
# >= 4.2.1 (the committed cassette is recorded against its desktop-2.16120.0 baseline, so an older
# CLI reports it stale) — see `harness/README.md`. 3.0.0 renamed the `l0_plugin_divergence` signal to
# `l0_host_config_contamination` and added the `allow_host_hooks` scenario key; the loader is a
# strictObject, so an older CLI hard-errors on a scenario using the new key rather than ignoring it.)
cowork-harness lint-skill   --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness analyze-skill --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness lint --strict --min-severity WARN harness/scenarios/
# `lint` only WARNS on an UNKNOWN KEY, so a scenario that lints clean can still be unloadable;
# this runs the real loader (no token, no Docker, writes nothing) to prove the suite actually loads.
# Since 3.2.0 lint is the STRICTER check for one class — an invalid enum value (`fidelity: bogus`,
# `result: succes`, `decide: allowe`) is an ERROR, where it used to lint clean and fail at load.
# The directory arm is NOT recursive and reports a `prompt:`-less file as *skipped*, not broken.
cowork-harness record harness/scenarios/ --dry-run --quiet
# CI also runs this one, and omitting it locally is how a stale cassette reaches a PR: a cassette
# records the SKILL's behaviour, so its staleness hash is tied to the skill's source and ANY edit
# under skills/ invalidates it. Re-record with:
#   cowork-harness record harness/scenarios/no-trigger.yaml --out harness/cassettes/no-trigger.cassette.json
cowork-harness verify-cassettes harness/cassettes --allow-empty
```

## cowork-harness dogfood suite (`harness/`)

`harness/` regression-tests this repo's own skill under the runtime contract of a cloud or local session. It is
maintainer CI, not part of the user-facing skill workflow. Full instructions: `harness/README.md`.

- **CI** (`.github/workflows/harness.yml`) runs the token-free static lane on every PR/push:
  `lint-skill --strict`, `analyze-skill --strict`, scenario `lint`, a `record --dry-run --quiet`
  load-check (catches an unloadable scenario that `lint` only warned on), and (once cassettes exist)
  a guarded `verify-cassettes` + `replay`.
- **Recording cassettes** and the live `container`-fidelity `run` need Docker + a staged Claude
  Desktop agent binary + a token — a maintainer step, not CI. Run `cowork-harness doctor --tier
  container` first.
- **Install caveat:** `npx cowork-harness@<ver>` can silently serve a stale cached CLI. Verify
  `cowork-harness --version` reports **4.2.x** (write-back detector landed in 1.1.0; the
  `verify-cassettes` claude.com handshake fix landed in 1.2.0); the CI job pins `cowork-harness@4.2.1`
  in an isolated prefix and asserts the version.

### Cassette privacy policy (public repo — BLOCKING)

Recorded cassettes capture real run transcripts and must be privacy-scanned before they are
committed to this public repo. **No cassette is committed without a green
`cowork-harness verify-cassettes harness/cassettes/<file>.cassette.json`** (PII + secret scan +
staleness), run with **no allowlist flags**. The CI `replay` lane runs `verify-cassettes` too, but
the blocking gate is at commit time — a leaked token or PII in a committed cassette is an
irreversible disclosure.

There are **no sanctioned allowlist entries.** Any `verify-cassettes` finding is treated as real and
must be investigated and the cassette re-recorded or scrubbed — never allowlisted away to force a
commit. (cowork-harness ≥1.16.0 no longer emits the benign `claude.com` MCP-handshake false-positive
that previously required a single `--allow-domain 'claude\.com'` exception; dropping that exception
makes the gate strictly tighter — a genuine `claude.com` leak elsewhere in a cassette is no longer
silently cleared.)

Design decisions and scope (why this suite is deliberately narrow, why the nightly live lane is
deferred, why the emitter was cut): `docs/internal/cowork-harness-integration-plan.md`.

## Architecture

- `skill-creator-plus/` — the plugin directory (installed by marketplace)
  - `.claude-plugin/plugin.json` — plugin metadata
  - `skills/skill-creator-plus/SKILL.md` — main skill instructions
  - `skills/skill-creator-plus/agents/` — subagent instructions (grader, comparator, analyzer)
  - `skills/skill-creator-plus/scripts/` — Python utilities for eval, benchmarking, packaging
  - `skills/skill-creator-plus/references/` — best practices and schema docs
  - `skills/skill-creator-plus/eval-viewer/` — browser-based eval result viewer

## Version Management

Single source of truth: `VERSION` file at repo root.
Use `./tools/bump-version.sh X.Y.Z` to propagate everywhere.
Never edit version fields manually in plugin.json or SKILL.md.

## Release Process

`main` is protected — changes land via pull request — and **cutting a release is a maintainer step,
not self-serve.** Don't push to `main` or push a tag without the maintainer's explicit go-ahead for
that release. (Admin bypass is enabled, so a direct push from a maintainer account *succeeds* and
merely prints `Bypassed rule violations` — the protection won't stop an accidental release, so the
approval is the real gate. Automated agents: this includes you; committing locally is not approval
to push.)

```bash
./tools/bump-version.sh X.Y.Z
git commit -am "chore: bump version to X.Y.Z"
# open a PR and get it merged, then tag the merge commit on main:
git tag vX.Y.Z
git push origin vX.Y.Z
```

Push the **tag by name**, not `git push --tags`: `.github/workflows/release.yml` triggers on
`push: tags: 'v*'`, so the tag alone is what cuts the release — `main` itself is already updated by
the merge.

CI creates a GitHub Release with a zip artifact automatically once the tag arrives.
