# Skill Creator Plus

<p align="center">
  <img src="assets/banner.png" alt="Skill Creator Plus" width="100%">
</p>

[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://yaniv-golan.github.io/skill-creator-plus/install-claude-desktop.html)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-plugin-F97316)](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/plugins)

A Claude skill for creating, testing, evaluating, and iteratively improving other Claude skills. Built-in benchmarking, blind A/B comparison, and description optimization.

## What It Does

Building good skills requires iteration: write, test, measure, improve, repeat. This skill automates the evaluation loop:

- **Create skills** from intent — captures requirements, success criteria, and writes a structured SKILL.md
- **Run evaluations** — parallel with-skill and baseline runs, timed and measured
- **Grade results** — automated assertion checking with pass/fail verdicts and evidence
- **Benchmark** — aggregated metrics with mean/stddev across multiple runs
- **Blind A/B comparison** — unbiased quality comparison between skill versions
- **Optimize descriptions** — train/test split evaluation loop to maximize trigger accuracy without overfitting
- **Package skills** — validate and bundle into distributable .skill format

## Relationship to skill-creator

Built on Anthropic's official [`skill-creator`](https://github.com/anthropics/claude-plugins-official) plugin (Apache 2.0). The core workflow, agents, eval viewer, and scripts are from the original. This version adds:

- **Anthropic's best practices reference** — 580 lines of patterns, description formula, structural patterns, troubleshooting guide, and checklist from Anthropic's official guide and internal lessons (`references/official-guide-patterns.md`)
- **Extended authoring guidance** — use case taxonomy, success criteria, full frontmatter reference, five structural patterns, technical rules, and pre-package validation checklist
- **Cowork feedback fix** — the built-in skill-creator's eval viewer silently fails in Cowork: you write feedback, click "Submit All Reviews", it says "saved" — but nothing is actually saved and Claude never receives your feedback. This version shows the feedback as copyable JSON so you can paste it into the chat.
- **Description optimizer actually works** — the built-in version calls the Anthropic SDK directly, which requires `ANTHROPIC_API_KEY` to be set separately — most Claude Code users don't have this, so description optimization silently crashes. This version uses `claude -p` instead, which piggybacks on your existing session auth

## Installation

### Claude Desktop

[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://yaniv-golan.github.io/skill-creator-plus/install-claude-desktop.html)

*— or install manually —*

1. Click **Customize** in the sidebar
2. Click **Browse Plugins**
3. Go to the **Personal** tab and click **+**
4. Choose **Add marketplace**
5. Type `yaniv-golan/skill-creator-plus` and click **Sync**

### Claude Code (CLI)

From your terminal:

```bash
claude plugin marketplace add https://github.com/yaniv-golan/skill-creator-plus
claude plugin install skill-creator-plus@skill-creator-plus-marketplace
```

Or from within a Claude Code session:

```
/plugin marketplace add yaniv-golan/skill-creator-plus
/plugin install skill-creator-plus@skill-creator-plus-marketplace
```

### Claude.ai (Web)

1. Download [`skill-creator-plus.zip`](https://github.com/yaniv-golan/skill-creator-plus/releases/latest/download/skill-creator-plus.zip)
2. Click **Customize** in the sidebar
3. Go to **Skills** and click **+**
4. Choose **Upload a skill** and upload the zip file

## Usage

The skill auto-activates when you ask to create, improve, or evaluate a skill. Examples:

```
Create a skill that reviews pull requests for security issues
```

```
Run evals on my skill and show me the results
```

```
Optimize my skill's description for better triggering
```

```
Do a blind A/B comparison between the old and new version of my skill
```

## How It Works

### 1. Create
Captures your intent through structured questions, researches existing patterns, then writes a SKILL.md with metadata, instructions, and test cases.

### 2. Evaluate
Spawns parallel runs (with-skill and baseline) on test prompts. While runs execute, drafts quantitative assertions. Grades results via the grader agent and shows them in an interactive browser-based viewer.

### 3. Improve
Analyzes evaluation results, identifies weaknesses, and rewrites the skill. Each iteration is benchmarked against the previous version.

### 4. Compare
For rigorous validation, runs blind A/B comparison: the comparator agent scores two outputs without knowing which skill produced them, then the analyzer agent unblinds and explains the differences.

### 5. Optimize Description
Generates trigger/non-trigger test queries, runs an optimization loop with train/test split, and selects the best-performing description.

## Components

| Component | Purpose |
|-----------|---------|
| `SKILL.md` | Main skill instructions and workflow |
| `agents/grader.md` | Evaluation assertion grader |
| `agents/comparator.md` | Blind A/B quality comparison |
| `agents/analyzer.md` | Post-comparison analysis and improvement suggestions |
| `scripts/run_eval.py` | Trigger evaluation runner |
| `scripts/run_loop.py` | Eval + improve optimization loop |
| `scripts/aggregate_benchmark.py` | Benchmark aggregation with statistics |
| `scripts/quick_validate.py` | Skill structure validation |
| `scripts/package_skill.py` | Skill packaging for distribution |
| `scripts/generate_report.py` | HTML report generation |
| `scripts/improve_description.py` | Description optimization via Claude |
| `eval-viewer/` | Interactive browser-based result viewer |
| `references/official-guide-patterns.md` | Anthropic's skill-building best practices |
| `references/schemas.md` | JSON schema definitions for all data formats |

## License

MIT
