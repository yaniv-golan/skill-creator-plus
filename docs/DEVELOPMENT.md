# Skill Creator Plus — Development Reference

## Quick Commands

```bash
# Validate skill structure
python skill-creator-plus/skills/skill-creator-plus/scripts/quick_validate.py skill-creator-plus/skills/skill-creator-plus
# JSON output for tooling: add --json. Exit codes: 0 valid, 1 invalid, 2 reserved (stdlib-only now), 3 path not found.

# Cross-runtime portability lint (stdlib-only; --target claude-code|claude-ai|cowork|all)
cd skill-creator-plus/skills/skill-creator-plus && python -m scripts.check_portability . --target all
# Rules: desc-over-hard-cap, listing-entry-truncation, listing-desc-drop-risk, subagent-dependency,
# claude-cli-dependency, browser-display-dependency, thirdparty-import (allowlisted against Cowork's
# preinstalled stack), delivery-tool-single-lane, delivery-conditional-deliverable.
# --strict gates on warnings/errors only; advisories report but never gate (add --strict-advisories
# to gate on those too). Exit codes: 0 no gating findings, 1 gated, 2 usage error, 3 path not found.
# Note this skill's own baseline: 3 advisories (subagent / claude-CLI / browser deps, all Claude-Code-
# first by design) — so `--target all` is exit 0, and `--target cowork --strict` is exit 1 on the
# browser-display warning. A NEW rule id is the regression signal, not a non-empty finding list.

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

# cowork-harness static checks on the shipped skill (token-free, no Docker; needs cowork-harness
# >= 1.16.0 — see `harness/README.md`)
cowork-harness lint-skill   --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness analyze-skill --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness lint harness/scenarios/
# `lint` only WARNS on an unknown key, so a scenario that lints clean can still be unloadable;
# this runs the real loader (no token, no Docker, writes nothing) to prove the suite actually loads.
cowork-harness record harness/scenarios/ --dry-run --quiet
```

## cowork-harness dogfood suite (`harness/`)

`harness/` regression-tests this repo's own skill under Claude Cowork's runtime contract. It is
maintainer CI, not part of the user-facing skill workflow. Full instructions: `harness/README.md`.

- **CI** (`.github/workflows/harness.yml`) runs the token-free static lane on every PR/push:
  `lint-skill --strict`, `analyze-skill --strict`, scenario `lint`, a `record --dry-run --quiet`
  load-check (catches an unloadable scenario that `lint` only warned on), and (once cassettes exist)
  a guarded `verify-cassettes` + `replay`.
- **Recording cassettes** and the live `container`-fidelity `run` need Docker + a staged Claude
  Desktop agent binary + a token — a maintainer step, not CI. Run `cowork-harness doctor --tier
  container` first.
- **Install caveat:** `npx cowork-harness@<ver>` can silently serve a stale cached CLI. Verify
  `cowork-harness --version` reports **1.16.x** (write-back detector landed in 1.1.0; the
  `verify-cassettes` claude.com handshake fix landed in 1.2.0); the CI job pins `cowork-harness@1.16.0`
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
