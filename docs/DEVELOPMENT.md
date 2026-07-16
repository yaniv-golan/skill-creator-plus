# Skill Creator Plus — Development Reference

## Quick Commands

```bash
# Validate skill structure
python skill-creator-plus/skills/skill-creator-plus/scripts/quick_validate.py skill-creator-plus/skills/skill-creator-plus
# JSON output for tooling: add --json. Exit codes: 0 valid, 1 invalid, 2 reserved (stdlib-only now), 3 path not found.

# Cross-runtime portability lint (stdlib-only; --target claude-code|claude-ai|cowork|all; --strict to gate)
cd skill-creator-plus/skills/skill-creator-plus && python -m scripts.check_portability . --target all

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

# cowork-harness static checks on the shipped skill (token-free, no Docker; needs cowork-harness >= 1.1.0)
cowork-harness lint-skill   --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness analyze-skill --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness lint harness/scenarios/
```

## cowork-harness dogfood suite (`harness/`)

`harness/` regression-tests this repo's own skill under Claude Cowork's runtime contract. It is
maintainer CI, not part of the user-facing skill workflow. Full instructions: `harness/README.md`.

- **CI** (`.github/workflows/harness.yml`) runs the token-free static lane on every PR/push:
  `lint-skill --strict`, `analyze-skill --strict`, scenario `lint`, and (once cassettes exist) a
  guarded `verify-cassettes` + `replay`.
- **Recording cassettes** and the live `container`-fidelity `run` need Docker + a staged Claude
  Desktop agent binary + a token — a maintainer step, not CI. Run `cowork-harness doctor --tier
  container` first.
- **Install caveat:** `npx cowork-harness@<ver>` can silently serve a stale cached CLI. Verify
  `cowork-harness --version` reports **1.1.x** (the artifact write-back detector landed in 1.1.0);
  the CI job pins `cowork-harness@1.1.0` in an isolated prefix and asserts the version.

### Cassette privacy policy (public repo — BLOCKING)

Recorded cassettes capture real run transcripts and must be privacy-scanned before they are
committed to this public repo. **No cassette is committed without a green
`cowork-harness verify-cassettes harness/cassettes/<file>.cassette.json --allow-domain 'claude\.com'`**
(PII + secret scan + staleness). The CI `replay` lane runs `verify-cassettes` too, but the blocking
gate is at commit time — a leaked token or PII in a committed cassette is an irreversible disclosure.

The **only** sanctioned allowlist entry is `claude.com` — it is Claude Code's own init metadata
(`websiteUrl: https://claude.com/claude-code`), appears in every cassette, and is benign. Any
**other** verify-cassettes finding must be investigated and the cassette re-recorded or scrubbed —
never allowlisted away to force a commit.

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

```bash
./tools/bump-version.sh X.Y.Z
git commit -am "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

CI creates a GitHub Release with a zip artifact automatically.
