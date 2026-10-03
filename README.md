# Skill Creator Plus

<p align="center">
  <img src="assets/banner.png" alt="Skill Creator Plus" width="100%">
</p>

[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://yaniv-golan.github.io/skill-creator-plus/install-claude-desktop.html)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-plugin-F97316)](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/plugins)

The skill that builds skills. Draft one and ship it in a single pass, or run evals against a baseline and iterate until it measurably works — targeting Claude Code, the Claude app's chat, or its cloud and local sessions (Claude Cowork, now part of Claude for accounts that have moved over) — runtimes that differ in ways that silently break skills. You can also just ask it how skills work. Based on Anthropic's official [`skill-creator`](https://github.com/anthropics/claude-plugins-official) plugin, with bug fixes and best practices baked in.

| | Official `skill-creator` | `skill-creator-plus` |
|---|---|---|
| Best practices guide | — | Patterns reference from Anthropic's guidance, plus this project's measured additions (labelled) |
| Script vs. Instruct guidance | — | Decision framework for when to bundle scripts vs. use instructions |
| Structure validation | Allowed keys, name format, length caps | Also type-checks Claude-specific fields, matches the name to the folder, and checks the 1,536-char listing cap, against the [agentskills.io](https://agentskills.io/specification) spec |
| Cross-runtime linting | — | 14 rules for what breaks outside Claude Code — sub-agent, `claude` CLI and browser dependencies, third-party imports, file delivery, compaction |
| Cloud and local session guidance | — | Runtime-specific guidance for the Claude app's cloud and local sessions ([below](#authoring-for-cowork)) |
| Claude Code runtime docs | — | Listing budget + per-skill degradation order, permission semantics, truncation caps, live-reload behavior — verified against 2.1.222–2.1.251 (listing budget re-verified at 2.1.280) |
| Eval viewer in cloud and local sessions | Silent fail on submit | Copyable JSON textarea (fixed) |
| Description optimizer | Runs `claude -p`; keeps the top score, no length preference | Runs `claude -p`, isolated from your installed skills when a credential is exported; length-aware selection + plateau early-stop; refuses to score a run it couldn't measure |
| Benchmarking script | Silent empty results | Fixed directory handling |
| Skill type taxonomy | — | 3 categories from Anthropic's guide + 9 types used inside Anthropic |
| Pre-packaging checklist | — | Official checklist built in |

## Why This Over the Built-in?

Anthropic ships a `skill-creator` plugin. It's good, but several parts are broken or missing:

- **Best practices guide included** — patterns, structural templates, troubleshooting guide, and checklists drawn from Anthropic's [Complete Guide to Building Skills for Claude](https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf) and Thariq's [Lessons from Building Claude Code Skills](https://x.com/trq212/status/2024574133011673516). Includes a "Script vs. Instruct" decision framework for when to bundle pre-made scripts vs. keep logic as instructions — covering context window efficiency, reliability, and auditability. This project's own measured runtime additions sit alongside, labelled as such. The built-in doesn't ship any of this.
- **A skill that works here can break there, silently** — the `claude` CLI is on PATH in Claude Code and was found in the Claude app's cloud and local sessions, but not in its chat runtime (Chat in the older Chat/Cowork picker; one check each), so gate a `claude -p` step on `command -v claude`; the Claude app's chat runtime typically has no sub-agent tool, so parallel eval runs have to collapse to serial there (a Claude app conversation running in a cloud session does have one — route by the tool list, not the product); an agent in a cloud or local session can't serve a local HTTP server and open it, so the eval viewer needs a static build; a third-party import there costs an install on every run, and egress is org-configurable, so a locked-down org can refuse it; and file delivery differs per surface — in a cloud session, writing a file is not delivering it. Structure validation can't see any of that, so there are two checks: `quick_validate` for structure, and a 14-rule portability linter for runtime assumptions — including the two ways compaction loses a skill. Both are stdlib-only, because they have to run inside the sandboxes they lint. Rule ids, flags and exit codes are in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).
- **Claude Code runtime docs** — the mechanics most skill authors hit the hard way, read out of the shipping binary rather than inherited from a blog post: overflow of the shared listing budget drops descriptions **per skill, least-recently-used first**, packing first-fit, so full and name-only entries coexist and a long description can lose to a shorter one; `allowed-tools` **grants** permission rather than requesting it; and compaction is a CHARACTER gate, not the documented token one, losing content two different ways — truncation keeps the first 19,900 characters and leaves a marker, while the combined cross-skill cap **zeroes** a skill outright with no marker and no entry. Verified against Claude Code 2.1.222–2.1.251; the listing budget re-verified at 2.1.280. Where the public docs and the binary disagree, the references ([patterns](skill-creator-plus/skills/skill-creator-plus/references/official-guide-patterns.md), [advanced features](skill-creator-plus/skills/skill-creator-plus/references/advanced-features.md)) say so and show which one shipped.

The eval viewer, description optimizer and benchmarking fixes are in the table above; see the [CHANGELOG](CHANGELOG.md) for the full list.

## Quick Start

Install (Claude Code):

```bash
claude plugin marketplace add https://github.com/yaniv-golan/skill-creator-plus
claude plugin install skill-creator-plus@skill-creator-plus-marketplace
```

Then just ask:

```
/skill-creator-plus:skill-creator-plus Create a skill that reviews pull requests for security issues
```

The skill takes it from there — intent capture, drafting, test cases, and delivery.

You can also just ask it a question. Mechanics are in scope on their own — frontmatter fields, path variables, size limits, directory layout, or what breaks across runtimes — however small the question.

> **Note:** If Anthropic's `skill-creator` is also available (installed in Claude Code, or built into your claude.ai account), Claude may pick that one instead. Remove or turn off the other one where your app allows it, or in Claude Code use `/skill-creator-plus:skill-creator-plus` to invoke it explicitly.

## How It Works

There are two routes, and the fast one is a real route rather than a shortcut.

### Route 1 — a working skill now

For when you want the skill itself, not an eval report:

1. **Draft** — captures your intent through structured questions, researches existing patterns, then writes a SKILL.md with metadata, instructions and test cases.
2. **Smoke-test every bundled script** — directly, on synthetic input with the problems planted: malformed rows, wrong delimiter, unusual encoding, empty and header-only files, a missing file. A script that only ever ran on clean input is untested.
3. **Validate** — `quick_validate` for structure, then `check_portability` for the runtime you're targeting.
4. **Package and deliver.**

Steps 2 and 3 *are* the verification when you skip evals. Shipping without eval evidence is fine; shipping with nothing exercised is not.

### Route 2 — evidence it works

For when you need to show the skill helps:

1. **Evaluate** — spawns parallel runs (with-skill and baseline) on test prompts. While runs execute, drafts quantitative assertions. Grades results via the grader agent and shows them in an interactive viewer, so you form your own opinion before anything is rewritten.
2. **Improve** — analyzes results, identifies weaknesses, rewrites the skill. Each iteration is benchmarked against the previous version.

Then repeat. Order is flexible, and an existing draft can join at step 1.

### Optional depth

- **Blind A/B comparison** — the comparator agent scores two outputs without knowing which skill produced them; the analyzer agent then unblinds and explains the differences.
- **Description optimization** — generates trigger and non-trigger queries, runs an optimization loop with a train/test split, and selects the best-performing description. A description is what decides whether your skill is ever invoked at all.

<a id="authoring-for-cowork"></a>
## Authoring for cloud and local sessions

Cloud and local sessions break assumptions that hold everywhere else, and they break them *quietly* — the write succeeds, the tool reports success, and the file is somewhere nobody will look. The skill knows about:

- **Where the workspace must live.** The skill directory is a read-only plugin mount, so the workspace can't sit beside it. The agent falls back to the session scratchpad — which in a cloud session is reclaimed at session end, destroying the skill it just built.
- **File tools and the shell don't share a working directory.** No single relative path is correct for both, so the identifier and the base have to stay apart.
- **Writing a file is not delivering it.** In a cloud session a file written and never presented through a tool is silently lost. Delivery is two steps, always taught in order.
- **A script's stdout is not delivery for text, either.** Tool-call output is collapsed in a cloud or local session's transcript, so anything the user actually needs to read has to be said, not printed.

Parts of this are authoring guidance rather than verified behavior, and the guidance says which is which. For the current, dated state of these runtimes — what was checked, when, and on which Desktop and agent builds — see [Writing skills that survive Cowork](https://ccinternals.dev/cowork/) on ccinternals.dev, which most of this guidance draws on. See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the linter's flags, rule ids and exit codes.

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
/skill-creator-plus:skill-creator-plus Create a skill that reviews pull requests for security issues
```

```
/skill-creator-plus:skill-creator-plus Run evals on my skill and show me the results
```

```
/skill-creator-plus:skill-creator-plus Optimize my skill's description for better triggering
```

```
/skill-creator-plus:skill-creator-plus Do a blind A/B comparison between the old and new version of my skill
```

```
/skill-creator-plus:skill-creator-plus Check whether my skill will work in Cowork
```

```
/skill-creator-plus:skill-creator-plus What happens to my skill when the context gets compacted?
```

## Badge

If you built a skill using Skill Creator Plus, add this badge to your README:

[![Built with Skill Creator Plus](https://img.shields.io/badge/Built_with-Skill_Creator_Plus-4ecdc4?style=flat-square)](https://github.com/yaniv-golan/skill-creator-plus)

```markdown
[![Built with Skill Creator Plus](https://img.shields.io/badge/Built_with-Skill_Creator_Plus-4ecdc4?style=flat-square)](https://github.com/yaniv-golan/skill-creator-plus)
```

## License

MIT — see [LICENSE](LICENSE). Built on Anthropic's skill-creator (Apache 2.0) — see [NOTICE](NOTICE).
