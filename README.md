# Skill Creator Plus

<p align="center">
  <img src="assets/banner.png" alt="Skill Creator Plus" width="100%">
</p>

[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://yaniv-golan.github.io/skill-creator-plus/install-claude-desktop.html)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-plugin-F97316)](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/plugins)

The skill that builds skills. Write a draft, run evals against a baseline, review results in an interactive viewer, improve, and repeat — until your skill actually works. Based on Anthropic's official [`skill-creator`](https://github.com/anthropics/claude-plugins-official) plugin, with bug fixes and best practices baked in.

## Why This Over the Built-in?

Anthropic ships a `skill-creator` plugin. It's good, but several parts are broken or missing:

- **Best practices guide included** — 580 lines of patterns, structural templates, troubleshooting guide, and checklists extracted from Anthropic's [Complete Guide to Building Skills for Claude](https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf) and Thariq's [Lessons from Building Claude Code Skills](https://x.com/trq212/status/2024574133011673516). The built-in doesn't ship any of this.
- **Eval viewer actually works in Cowork** — the built-in silently fails: you write feedback, click "Submit All Reviews", it says "saved" — but nothing reaches Claude. This version reliably shows copyable JSON you can paste back.
- **Description optimizer doesn't crash** — the built-in calls the Anthropic SDK directly, requiring a separate `ANTHROPIC_API_KEY` most users don't have. This version uses `claude -p`, which just works with your existing session.
- **Benchmarking script fixed** — the built-in's aggregation script silently produces empty results due to undocumented directory structure requirements. Fixed and tested.

See the [CHANGELOG](CHANGELOG.md) for the full list of fixes.

## Quick Start

Install (Claude Code):

```bash
claude plugin marketplace add https://github.com/yaniv-golan/skill-creator-plus
claude plugin install skill-creator-plus@skill-creator-plus-marketplace
```

Then just ask:

```
/skill-creator-plus Create a skill that reviews pull requests for security issues
```

The skill takes it from there — intent capture, drafting, test cases, evaluation, and iteration.

> **Note:** If you also have Anthropic's built-in `skill-creator` installed, Claude may pick that one instead. Either uninstall the built-in, or use `/skill-creator-plus` to invoke this version explicitly.

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

## Usage Examples

```
/skill-creator-plus Create a skill that reviews pull requests for security issues
```

```
/skill-creator-plus Run evals on my skill and show me the results
```

```
/skill-creator-plus Optimize my skill's description for better triggering
```

```
/skill-creator-plus Do a blind A/B comparison between the old and new version of my skill
```

## Badge

If you built a skill using Skill Creator Plus, add this badge to your README:

[![Built with Skill Creator Plus](https://img.shields.io/badge/Built_with-Skill_Creator_Plus-4ecdc4?style=flat-square)](https://github.com/yaniv-golan/skill-creator-plus)

```markdown
[![Built with Skill Creator Plus](https://img.shields.io/badge/Built_with-Skill_Creator_Plus-4ecdc4?style=flat-square)](https://github.com/yaniv-golan/skill-creator-plus)
```

## License

MIT — see [LICENSE](LICENSE). Built on Anthropic's skill-creator (Apache 2.0) — see [NOTICE](NOTICE).
