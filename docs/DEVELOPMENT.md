# Skill Creator Plus — Development Reference

## Quick Commands

```bash
# Validate skill structure
python skill-creator-plus/skills/skill-creator-plus/scripts/quick_validate.py skill-creator-plus/skills/skill-creator-plus
# JSON output for tooling: add --json. Exit codes: 0 valid, 1 invalid, 2 PyYAML missing, 3 path not found.

# Syntax-check all scripts
for f in skill-creator-plus/skills/skill-creator-plus/scripts/*.py; do python -c "import py_compile; py_compile.compile('$f', doraise=True)"; done

# Install the validator's one runtime dep (PyYAML)
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
```

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
