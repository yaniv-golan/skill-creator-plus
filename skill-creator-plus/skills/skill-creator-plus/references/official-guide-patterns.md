# Official Skill-Building Patterns & Best Practices

Sources:
- Anthropic's "The Complete Guide to Building Skills for Claude" (2026)
- Thariq's "Lessons from Building Claude Code Skills: How We Use Skills" (Mar 2026) — battle-tested insights from hundreds of skills in active use at Anthropic

Read this reference when designing or reviewing skills — it contains the canonical patterns, checklists, troubleshooting guidance, and hard-won practical lessons.

---

## Table of Contents

1. [Use Case Categories](#use-case-categories)
2. [Expanded Skill Type Taxonomy](#expanded-skill-type-taxonomy)
3. [Description Field Formula](#description-field-formula)
4. [Success Criteria](#success-criteria)
5. [Five Skill Patterns](#five-skill-patterns)
6. [Instructions Best Practices](#instructions-best-practices)
7. [Practical Lessons from Anthropic's Internal Use](#practical-lessons)
8. [Technical Rules](#technical-rules)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Quick Checklist](#quick-checklist)

---

## Use Case Categories

Most skills fall into one of three categories. Identifying which one early shapes the design.

### Category 1: Document & Asset Creation
Creating consistent, high-quality output (documents, presentations, apps, designs, code).

Key techniques:
- Embedded style guides and brand standards
- Template structures for consistent output
- Quality checklists before finalizing
- No external tools required — uses Claude's built-in capabilities

### Category 2: Workflow Automation
Multi-step processes that benefit from consistent methodology, including coordination across multiple MCP servers.

Key techniques:
- Step-by-step workflow with validation gates
- Templates for common structures
- Built-in review and improvement suggestions
- Iterative refinement loops

### Category 3: MCP Enhancement
Workflow guidance to enhance the tool access an MCP server provides.

Key techniques:
- Coordinates multiple MCP calls in sequence
- Embeds domain expertise
- Provides context users would otherwise need to specify
- Error handling for common MCP issues

---

## Expanded Skill Type Taxonomy

Source: Thariq's post. Anthropic internally uses a more granular 9-type taxonomy. When helping a user figure out what kind of skill to build, this list can help them see if there's an obvious fit — and what techniques work best for that type.

### 1. Library & API Reference
Skills that explain how to correctly use a library, CLI, or SDK — especially internal ones or common libraries Claude struggles with. Often include reference code snippets and a list of gotchas.

Examples: `billing-lib` (internal billing library edge cases), `internal-platform-cli` (every subcommand with usage examples), `frontend-design` (make Claude better at your design system)

### 2. Product Verification
Skills that test or verify that code is working. Often paired with external tools like Playwright, tmux, etc. **Anthropic considers these worth a week of investment** — they're extremely useful for ensuring Claude's output is correct.

Techniques: Record videos of output, enforce programmatic assertions on state at each step, include verification scripts in the skill.

Examples: `signup-flow-driver` (runs signup → email verify → onboarding in headless browser), `checkout-verifier` (drives checkout UI with Stripe test cards)

### 3. Data Fetching & Analysis
Skills that connect to data and monitoring stacks. Include libraries for fetching data with credentials, specific dashboard IDs, and instructions on common workflows.

Examples: `funnel-query` (which events to join for signup → activation → paid), `cohort-compare` (compare retention, flag significant deltas), `grafana` (datasource UIDs, cluster names, problem → dashboard lookup)

### 4. Business Process & Team Automation
Skills that automate repetitive workflows into one command. Usually simple instructions but may depend on other skills or MCPs. **Key technique: save previous results in log files** so the model can stay consistent and reflect on previous executions.

Examples: `standup-post` (aggregates ticket tracker + GitHub + prior Slack → formatted standup), `create-ticket` (enforces valid enum values, required fields, plus post-creation workflow), `weekly-recap` (merged PRs + closed tickets + deploys → formatted recap)

### 5. Code Scaffolding & Templates
Skills that generate framework boilerplate. Combine with scripts that can be composed. Especially useful when scaffolding has natural language requirements that can't be purely covered by code.

Examples: `new-<framework>-workflow` (scaffolds service/workflow/handler with your annotations), `new-migration` (migration file template plus common gotchas), `create-app` (new internal app with auth, logging, deploy config pre-wired)

### 6. Code Quality & Review
Skills that enforce code quality and help review code. Can include deterministic scripts for maximum robustness. Consider running automatically as hooks or in CI.

Examples: `adversarial-review` (spawns a fresh-eyes subagent to critique, iterates until findings degrade to nitpicks), `code-style` (enforces styles Claude doesn't do well by default), `testing-practices` (how to write tests and what to test)

### 7. CI/CD & Deployment
Skills that fetch, push, and deploy code. May reference other skills for data collection.

Examples: `babysit-pr` (monitors PR → retries flaky CI → resolves merge conflicts → auto-merge), `deploy-<service>` (build → smoke test → gradual rollout with error-rate comparison → auto-rollback), `cherry-pick-prod` (isolated worktree → cherry-pick → conflict resolution → PR with template)

### 8. Runbooks
Skills that take a symptom (Slack thread, alert, error signature), walk through a multi-tool investigation, and produce a structured report.

Examples: `<service>-debugging` (maps symptoms → tools → query patterns for high-traffic services), `oncall-runner` (fetches alert → checks usual suspects → formats finding), `log-correlator` (given a request ID, pulls matching logs from every system)

### 9. Infrastructure Operations
Skills for routine maintenance and operational procedures — especially destructive actions that benefit from guardrails.

Examples: `<resource>-orphans` (finds orphaned pods/volumes → posts to Slack → soak period → user confirms → cleanup), `dependency-management` (your org's dependency approval workflow), `cost-investigation` ("why did our bill spike" with specific buckets and query patterns)

---

## Description Field Formula

The `description` field is the primary — and on most hosts, the **only** — signal the agent uses to decide whether to load a skill. Write it to stand alone.

```
[What it does] + [When to use it] + [Key capabilities]
```

### Portable rules (apply to every agentskills.io-compatible host)

- MUST express BOTH what the skill does AND when to use it — in `description` alone.
- `description` field cap: **1,024 characters** (per the agentskills.io spec).
- No XML tags (`<` `>`).
- Include specific phrases users might say; mention relevant file types if applicable.

### Claude-specific addenda (Claude Code, verified against 2.1.222)

- **`when_to_use`** is an optional companion field. Claude Code renders the listing entry as `<name>: <description> - <when_to_use>`. Non-Claude hosts ignore it entirely — **never move trigger-critical content out of `description` into `when_to_use`**. Under Cowork it appears to be only *half* visible: the session puts two different skill listings in front of the model and only one of them carries `when_to_use` (see `references/environments.md` → *Two skill listings under Cowork*). That is a second, mechanism-level reason the field must never be load-bearing.
- **Combined listing-entry cap: 1,536 characters** for `description + when_to_use`. This is the default of the `skillListingMaxDescChars` setting, not a hard-coded constant. Above it, Claude truncates the entry.
- **The listing budget is shared, and overflow degrades per skill — not all at once.** Every skill competes for `contextWindow × 4 × skillListingBudgetFraction` characters (fraction defaults to `0.01`): ~8,000 chars at a 200 K context window, **~40,000 at 1 M**. On overflow Claude ranks skills by recency-weighted usage — `usageCount × max(0.5^(daysSinceLastUse/7), 0.1)` — then grants each its full description while budget remains; whatever no longer fits renders as name-only. **The skills you use keep their descriptions; the ones you never touch lose theirs first.** Bundled prompt skills, and skills set to `name-only`, are protected and never compete.

  Two consequences for authors. A bloated `description` mostly costs *itself* and the least-recently-used skills below it — it does **not** silently blank the listing for everyone, so there is no single "offender" to hunt. And the skill most likely to lose its description is the one nobody has invoked lately, which is exactly the skill whose triggering you would then be unable to debug. Diagnose with `/doctor` (estimates listing cost and names the biggest contributors) and `/context` (its Skills row reports post-budget size). Tuning knobs: `skillListingBudgetFraction`, `skillListingMaxDescChars`, per-skill `skillOverrides: {<skill>: on|name-only|user-invocable-only|off}`, and the `SLASH_COMMAND_TOOL_CHAR_BUDGET` env override.

### Good examples (portable)

```
# Good — specific and actionable; works on any host
description: Analyzes Figma design files and generates developer handoff
documentation. Use when user uploads .fig files, asks for "design specs",
"component documentation", or "design-to-code handoff".

# Good — includes trigger phrases
description: Manages Linear project workflows including sprint planning,
task creation, and status tracking. Use when user mentions "sprint",
"Linear tasks", "project planning", or asks to "create tickets".

# Good — clear value proposition
description: End-to-end customer onboarding workflow for PayFlow. Handles
account creation, payment setup, and subscription management. Use when
user says "onboard new customer", "set up subscription", or "create
PayFlow account".
```

### Good example (Claude-only split, optional)

```
# Claude-targeted: when_to_use adds extra trigger phrases without removing anything from description
description: Analyzes Figma design files and generates developer handoff
documentation. Handles .fig uploads, spec generation, and code stubs.
when_to_use: Also trigger on "design specs", "component documentation",
"design-to-code", or "handoff doc".
```

Note: `description` still fully explains the skill. `when_to_use` only adds Claude-listing phrases. A user on Gemini CLI reading the description alone still understands the skill.

### Bad examples

```
# Too vague
description: Helps with projects.

# Missing triggers
description: Creates sophisticated multi-page documentation systems.

# Too technical, no user triggers
description: Implements the Project entity model with hierarchical relationships.

# Non-portable: load-bearing content in Claude-only field
description: A documentation tool.
when_to_use: Use when user uploads .fig files, asks for design specs or
handoff docs. Handles Figma parsing and code generation.

# Bloated — risks collapsing the whole Claude listing
description: A comprehensive tool for handling every possible variant of …
when_to_use: Use when the user does A, B, C, D, E, F, G … [2,000 chars]
```

---

## Success Criteria

Define these before building. They're aspirational targets — rough benchmarks rather than precise thresholds.

### Quantitative Metrics
- **Skill triggers on 90% of relevant queries**
  - How to measure: Run 10-20 test queries. Track how many trigger automatically vs. require explicit invocation.
- **Completes workflow in X tool calls**
  - How to measure: Compare the same task with and without the skill. Count tool calls and total tokens.
- **0 failed API calls per workflow**
  - How to measure: Monitor MCP server logs during test runs. Track retry rates and error codes.

### Qualitative Metrics
- **Users don't need to prompt Claude about next steps**
  - How to assess: During testing, note how often you need to redirect or clarify. Ask beta users for feedback.
- **Workflows complete without user correction**
  - How to assess: Run the same request 3-5 times. Compare outputs for structural consistency and quality.
- **Consistent results across sessions**
  - How to assess: Can a new user accomplish the task on first try with minimal guidance?

---

## Five Skill Patterns

### Pattern 1: Sequential Workflow Orchestration
**Use when:** Users need multi-step processes in a specific order.

```
## Workflow: Onboard New Customer
### Step 1: Create Account
Call MCP tool: `create_customer`
Parameters: name, email, company

### Step 2: Setup Payment
Call MCP tool: `setup_payment_method`
Wait for: payment method verification

### Step 3: Create Subscription
Call MCP tool: `create_subscription`
Parameters: plan_id, customer_id (from Step 1)
```

Key techniques: Explicit step ordering, dependencies between steps, validation at each stage, rollback instructions for failures.

### Pattern 2: Multi-MCP Coordination
**Use when:** Workflows span multiple services.

```
### Phase 1: Design Export (Figma MCP)
1. Export design assets from Figma
2. Generate design specifications

### Phase 2: Asset Storage (Drive MCP)
1. Create project folder in Drive
2. Upload all assets

### Phase 3: Task Creation (Linear MCP)
1. Create development tasks
2. Attach asset links to tasks
```

Key techniques: Clear phase separation, data passing between MCPs, validation before moving to next phase, centralized error handling.

### Pattern 3: Iterative Refinement
**Use when:** Output quality improves with iteration.

```
### Initial Draft
1. Fetch data via MCP
2. Generate first draft report

### Quality Check
1. Run validation script: `scripts/check_report.py`
2. Identify issues

### Refinement Loop
1. Address each identified issue
2. Regenerate affected sections
3. Re-validate
4. Repeat until quality threshold met
```

Key techniques: Explicit quality criteria, iterative improvement, validation scripts, know when to stop iterating.

### Pattern 4: Context-Aware Tool Selection
**Use when:** Same outcome, different tools depending on context.

```
### Decision Tree
1. Check file type and size
2. Determine best storage location:
   - Large files (>10MB): Use cloud storage MCP
   - Collaborative docs: Use Notion/Docs MCP
   - Code files: Use GitHub MCP
   - Temporary files: Use local storage

### Provide Context to User
Explain why that storage was chosen
```

Key techniques: Clear decision criteria, fallback options, transparency about choices.

### Pattern 5: Domain-Specific Intelligence
**Use when:** Your skill adds specialized knowledge beyond tool access.

```
### Before Processing (Compliance Check)
1. Fetch transaction details via MCP
2. Apply compliance rules:
   - Check sanctions lists
   - Verify jurisdiction allowances
   - Assess risk level
3. Document compliance decision

### Audit Trail
- Log all compliance checks
- Record processing decisions
- Generate audit report
```

Key techniques: Domain expertise embedded in logic, compliance before action, comprehensive documentation, clear governance.

---

## Instructions Best Practices

### Be Specific and Actionable

Good:
```
Run `python scripts/validate.py --input {filename}` to check data format.
If validation fails, common issues include:
- Missing required fields (add them to the CSV)
- Invalid date formats (use YYYY-MM-DD)
```

Bad:
```
Validate the data before proceeding.
```

### Reference Bundled Resources Clearly

```
Before writing queries, consult `references/api-patterns.md` for:
- Rate limiting guidance
- Pagination patterns
- Error codes and handling
```

### Include Error Handling

```
## Common Issues

### MCP Connection Failed
If you see "Connection refused":
1. Verify MCP server is running: Check Settings > Extensions
2. Confirm API key is valid
3. Try reconnecting: Settings > Extensions > [Your Service] > Reconnect
```

### Use Progressive Disclosure
Keep SKILL.md focused on core instructions. Move detailed documentation to `references/` and link to it.

### Bundle Scripts for Programmatic Validation
For critical validations, bundle a script rather than relying on language instructions. Code is deterministic; language interpretation isn't.

### Combat Model "Laziness"
Add explicit encouragement for thoroughness:
```
## Performance Notes
- Take your time to do this thoroughly
- Quality is more important than speed
- Do not skip validation steps
```

Note: Adding this to user prompts is more effective than in SKILL.md.

---

## Practical Lessons from Anthropic's Internal Use

Source: Thariq's post. These are hard-won lessons from hundreds of skills in active use at Anthropic.

### Don't State the Obvious
Claude already knows a lot about coding and has strong default opinions. If your skill is primarily about knowledge, focus on information that **pushes Claude out of its normal way of thinking** — the non-obvious stuff, the org-specific conventions, the places where Claude's defaults are wrong. The frontend-design skill at Anthropic, for example, was built by iterating with customers on improving Claude's design taste, specifically avoiding Claude's classic patterns like the Inter font and purple gradients.

### Build a Gotchas Section
**The highest-signal content in any skill is the Gotchas section.** These should be built up from common failure points that Claude runs into when using your skill. Ideally, you update your skill over time to capture these gotchas as they emerge. This is the section that delivers the most value per token.

### Avoid Railroading Claude
Claude will generally try to stick to your instructions, and because skills are reusable across many situations, **be careful of being too specific**. Give Claude the information it needs, but give it flexibility to adapt to the situation. Overly rigid instructions that work for one test case may fail for the next user's slightly different context.

### Think Through the Setup
Some skills need context from the user (e.g., which Slack channel to post to). A good pattern: store setup information in a `config.json` file in the skill directory. If the config is not set up, the agent can ask the user for information. You can instruct Claude to use the AskUserQuestion tool for structured, multiple-choice setup questions.

### The Description Field Is a Trigger, Not a Summary
When Claude starts a session, it builds a listing of every available skill with its description. This is what Claude scans to decide "is there a skill for this request?" — which means the description is not a summary of what the skill contains. It's a description of **when to trigger**. Write it accordingly.

### Memory & Storing Data
Skills can include a form of memory by storing data within them. This can be anything from a simple append-only text log to JSON files to a SQLite database. For example, a standup skill might keep a `standups.log` with every post it writes, so the next time it runs, Claude reads its own history and can tell what's changed since yesterday.

Important: Data stored in the skill directory may be deleted when you upgrade the skill. For persistent data, use `${CLAUDE_PLUGIN_DATA}` which provides a stable folder per plugin.

### Store Scripts & Let Claude Compose

One of the most powerful things you can give Claude is code. Giving Claude scripts and libraries lets it spend its turns on **composition** — deciding what to do next — rather than reconstructing boilerplate.

**Concrete example:** A data science skill bundles `scripts/event_helpers.py` with functions like `fetch_events()`, `filter_by_date()`, and `aggregate_by_user()`. Without these, Claude writes a 50-line data-fetching function from scratch in every session — consuming context, risking subtle bugs, and wasting turns. With them, Claude writes a short composition script:

```python
from event_helpers import fetch_events, aggregate_by_user
data = fetch_events("signup", start="2026-01-01")
result = aggregate_by_user(data)
```

Claude spends its turns on *what analysis to run*, not on *how to fetch data*.

#### Why Offload to Scripts

Pre-made scripts are what turn skills from handy prompt bundles into production-grade, executable packages. When Claude runs a bundled script, **only the output enters the context window — not the script's source code.** This is the core leverage:

- **Context window efficiency** — a bundled script is one Bash call whose output enters context; LLM-generated code loads the full source into context and compounds across multi-step workflows and subagents
- **Reliability** — a bundled script is tested, debugged once, and runs identically every invocation; LLM-generated code is a fresh roll each time, with risk of subtle variation, hallucinated logic, or edge-case bugs
- **Speed** — no waiting for the LLM to write, debug, and iterate on code; scripts execute instantly in the native environment
- **Auditability** — scripts are version-controlled, reviewable separately, and easy to test independently of the skill; this matters for shared/distributed skills where users need to trust the code
- **Composition** — Claude stays in the high-level reasoning role (deciding *what to do*) while scripts handle the heavy lifting the model isn't great at (precise file I/O, custom computations, data transforms, format conversions)

#### When to Script vs. When to Instruct

Not everything belongs in a script. Use this framework to decide what should be code vs. what should stay as SKILL.md instructions.

**Script when the work is deterministic and repeatable:**
- Data transformation, format conversion, file I/O (e.g., CSV→JSON, DOCX generation, PDF processing)
- Validation with fixed rules (schema checks, required fields, regex patterns)
- API calls with specific auth/endpoint details
- Computationally intensive operations (data analysis, image conversion, custom CLI wrappers)
- Any logic where 2-3 independent test runs all produce essentially the same helper code

**Instruct when the work requires judgment or adaptability:**
- Subjective decisions (tone, emphasis, what to include/exclude)
- Context-dependent choices (which approach fits this user's situation)
- Flexible error recovery (interpreting unexpected results, deciding next steps)
- Workflow orchestration where the sequence may vary based on intermediate results

**The convergence signal:** During testing, if 2-3 independent runs each produce similar helper scripts (e.g., all three write a `build_chart.py` with the same matplotlib boilerplate), that's a strong signal to bundle the script. The logic has converged — stop letting Claude reinvent it.

**Example decision walkthrough:** A report-generation skill needs to (1) fetch data from an API, (2) clean/transform it, (3) decide what's interesting, (4) write the narrative, (5) format as PDF.
- Steps 1, 2, 5 → **Script.** Deterministic, same every time. Only the output (fetched data, cleaned data, PDF path) enters context.
- Steps 3, 4 → **Instruct.** Requires judgment about what matters and how to frame it.

### Declare at authoring time, probe at run time — never detect the host

A skill that must behave differently on different surfaces has two honest levers, and identity is
neither of them.

**Authoring time: declare.** `--target claude-code|claude-ai|cowork|all` states where the skill is
meant to run, and the linter checks the skill against that. This is a fact about intent, fixed when
you write it.

**Run time: probe for the capability, not the host.** Branch on *whether the thing you need is
there*, never on *which product you think you are in*. The delivery rule already works this way:
"scan your available tools for one whose description says it sends files to the user; if one exists
you must call it." It names no tool and no runtime, so it stays correct when a surface adds a tool,
renames one, or ships it behind a per-account gate.

**Why not an environment check.** The obvious idea is a marker like `CLAUDE_CODE_IS_COWORK`. It
fails in the worst possible way: a skill spans two execution contexts, and the shell context is
sealed — none of those markers survive into it. So the check returns "not Cowork" *in exactly the
configuration you most needed to detect*, silently, and every branch downstream is wrong. Host
identity is also the least stable thing to key on: within a single product name, the shell's working
directory has been mis-described in shipped prompt text, an in-app browser has appeared behind
per-account gates, and one tool has changed its input schema by session kind while keeping its name.
A skill keyed to "am I in X" inherits all of that. A skill keyed to "can I see what I need" does not.

**Paths are the case where the right answer is to probe for nothing at all.** A bundled script is
tempted to work out its own output location. Don't: the caller already knows it, holds the file
tools, and is the only party that can name a path the user will see. The caller resolves the
destination once and passes it as an absolute path; the script accepts it and echoes back what it
actually wrote. A script with no caller takes the destination as a **required argument and fails
loudly when it is missing** — it never invents a directory.

That last clause is load-bearing, and here is the failure it prevents. A probe of the shape
"if a Cowork-shaped mount is visible, write there, otherwise write to `outputs/`" looks fail-safe
and is not: on a surface where the shell already starts *inside* the outputs directory, the mount is
not visible, the fallback appends a second level, and you have re-created the `outputs/outputs/`
doubling — silently. One bit of evidence cannot separate three or more surfaces. A probe that
guesses is worse than an argument that is missing, because the missing argument is loud.

### Claude-specific frontmatter: what these fields actually do

`SKILL.md` states the rules; this is the mechanism behind them.

**`when_to_use`.** Claude Code joins it with `description` in its skill listing, and the combined pair is capped at 1,536 characters there. Non-Claude hosts ignore the field entirely, so trigger information placed only here is invisible to them. Under Cowork it is worse than non-portable: the session appears to show the model **two** listings and only one carries `when_to_use` (see `references/environments.md` → *Two skill listings under Cowork*), so it is partially invisible even on Claude. Keep `description` self-sufficient and treat `when_to_use` as additive phrasing only.

**`allowed-tools` / `disallowed-tools` / `shell`.** `allowed-tools` **grants**: it pre-approves tools for the invoking turn so Claude uses them without a permission prompt, and the grant clears on the user's next message. Populating it does **not** cause a prompt. `disallowed-tools` is the denylist that removes tools while the skill is active. `shell` only selects an interpreter (`bash`/`powershell`) and carries no permission semantics.

The one real gate is **workspace trust**: for a skill in a project's `.claude/skills/`, its capability frontmatter (`allowed-tools`, `hooks`) takes effect only after the trust dialog is accepted for that folder — once per folder, not per invocation. Review project skills before trusting a repo; a skill can grant itself broad tool access. MCP-sourced and shared-memory skills drop these fields entirely — see the carve-outs below.

### A default body skeleton (optional)

Nothing requires a particular section order, and a skill whose shape follows its own workflow is
usually better than one bent to a template. But starting from nothing costs time, so if no structure
suggests itself:

**Workflow** (the steps, in order) → **Options** (the decisions the user gets) → **Interpretation**
(how to read what comes back) → **Gotchas** (what goes wrong and what to do) → **Adjacent inputs**
(neighbouring cases and where they route instead).

**Gotchas is the highest-signal section** — it is where a skill stops restating what a capable model
already infers and starts carrying knowledge the model does not have. If a section is thin, cut it;
deviate wherever the work has a different shape. This is a starting point, not a form to fill in.

### Designing Scripts for Agent Use

A script that works fine for a human can be unusable for an agent. When an agent runs your script, it reads stdout and stderr to decide what to do next — design choices that seem cosmetic to a human are load-bearing for agents. Apply these conventions to every script you bundle.

**Accept absolute output paths, and echo back the absolute path you actually wrote.** A script runs under the shell, whose working directory is not the one the calling agent's file tools use. A relative output path can land somewhere neither the user nor the agent can reach, and the script will report success anyway. Resolve the path and print it — a bundled script is the only component that can honestly report where the bytes went, because `Write`'s own result echoes the path it was *given*, not a resolved one. Related: shell calls are independent, with no cwd carried between them, so a `cd` in one call cannot set up state for the next.

**When your skill text names a sandbox path, phrase it as the shell's location or a script's argument — never as a file-tool write target.** Static checkers flag prose describing a file-tool write/save/read/edit to a VM path (that operation really is denied), while "the shell starts in `<path>`" or "pass `<path>` to the script" is both correct and clean. A skill that gets this backwards fails its own author's lint.

**Non-interactive only.** Agents run in non-interactive shells. A script that blocks on a TTY prompt, password input, or confirmation menu hangs forever. Accept all input via flags, environment variables, or stdin — never `input()`, `read`, or interactive selection libraries. If a required value is missing, fail fast with a clear error stating what's needed.

```
# Bad: hangs waiting for input
$ python scripts/deploy.py
Target environment: _

# Good: clear error with guidance
$ python scripts/deploy.py
Error: --env is required. Options: development, staging, production.
Usage: python scripts/deploy.py --env staging --tag v1.2.3
```

**Document the interface with `--help`.** The agent learns what your script does primarily by running `--help`. Include a one-line description, all flags with their meanings, and 1–2 example invocations. Keep it concise — the output enters the agent's context window.

**Structured output, not free-form text.** Prefer JSON, CSV, or TSV over whitespace-aligned tables. Structured formats are unambiguous to parse, compose with `jq`/`cut`/`awk`, and survive minor changes without breaking downstream parsing. Send data to stdout and progress/diagnostics to stderr so the agent can capture clean output without losing diagnostic information.

**Helpful error messages.** When the agent gets an error, the message directly shapes its next attempt. "Error: invalid input" wastes a turn. State what went wrong, what was expected, and what to try:

```
Error: --format must be one of: json, csv, table.
       Received: "xml"
```

**Meaningful exit codes.** Use distinct exit codes for different failure types (e.g., `0` success, `1` invalid args, `2` not found, `3` auth failure). Document them in `--help` so the agent knows what each code means and can branch accordingly.

**Idempotent by default.** Agents may retry commands after a partial failure or timeout. "Create if not exists" is safer than "create and fail on duplicate." Where genuine destructive operations are unavoidable, require an explicit `--confirm` or `--force` flag rather than running silently.

**Dry-run support for destructive operations.** A `--dry-run` flag lets the agent preview what will happen and surface it to the user before committing. This pairs naturally with the [Plan-validate-execute](#validation-loops) pattern.

**Predictable output size.** Many agent harnesses truncate tool output beyond a threshold (often 10–30 K characters), silently dropping critical information. If your script can produce large output, default to a summary or a reasonable limit and support pagination flags (`--limit`, `--offset`). For genuinely large output that doesn't paginate, require an `--output FILE` flag so the agent explicitly opts in to capturing it on disk.

**Inline dependencies where the ecosystem supports it.** Use [PEP 723](https://peps.python.org/pep-0723/) for Python (run with `uv run`), Deno's `npm:`/`jsr:` specifiers, Bun auto-install, or `bundler/inline` for Ruby. This lets the script run with a single command — no separate manifest file, no install step, no environment surprises.

```python
# /// script
# dependencies = ["beautifulsoup4>=4.12,<5"]
# ///

from bs4 import BeautifulSoup
# ...
```

The common thread: scripts are agent tools, not human CLIs. Design them so a fresh agent reading only `--help` can use them correctly on the first try.

### On-Demand Hooks
Skills can include hooks that are only activated when the skill is called, lasting for the duration of the session. Use this for opinionated hooks that you don't want running all the time but are extremely useful sometimes. Examples:
- `/careful` — blocks rm -rf, DROP TABLE, force-push, kubectl delete via PreToolUse matcher on Bash
- `/freeze` — blocks any Edit/Write that's not in a specific directory

### Composing Skills
Skills can depend on each other. You can reference other skills by name in your instructions, and the model will invoke them if they're installed. Formal dependency management doesn't exist yet, but this pattern works today.

### Measuring Skill Usage
To understand how a skill is doing, consider using a PreToolUse hook to log skill usage. This helps find skills that are popular or undertriggering compared to expectations.

### Skills Start Small and Grow
Most of Anthropic's best skills began as just a few lines and a single gotcha, then got better because people kept adding to them as Claude hit new edge cases. Don't try to make the perfect skill on day one — start small, use it, and iterate.

---

## Technical Rules

### Naming
- **SKILL.md**: Must be exactly `SKILL.md` (case-sensitive). No variations.
- **Skill folder**: Use kebab-case only (e.g., `notion-project-setup`). No spaces, underscores, or capitals.
- **name field**: kebab-case, no spaces or capitals, should match folder name.

### Additional Frontmatter Fields
Beyond the required `name` and `description`, these optional fields give you more control:

- **`allowed-tools`**: Pre-approves tools for the turn that invokes the skill — Claude may use them without a permission prompt, and the grant clears on the user's next message (e.g. `allowed-tools: Read, Grep, Glob`). It is a **grant, not a restriction**. For a project-level skill it activates only once the folder's workspace-trust dialog is accepted.
- **`disallowed-tools`**: The denylist counterpart — removes tools while the skill is active. Use this (not `allowed-tools`) to stop a skill from making unintended edits or running commands.
- **`disable-model-invocation: true`**: Prevents Claude from auto-triggering the skill. It becomes slash-command only (e.g., `/deploy`). Use this for skills with side effects like deploying, sending messages, or deleting resources — anything where you don't want Claude firing it on its own.
- **`context: fork`**: Forces the skill to run in a separate subagent context, keeping your main conversation clean. Use for research-heavy skills that would otherwise bloat the main context window. Note: this only makes sense for skills that contain an actual task, not for skills that are just guidelines.
- **`background: false`** (with `context: fork`): Waits for the forked subagent's result in the invoking turn rather than backgrounding it. Use when the skill needs the subagent's output to continue. Requires Claude Code 2.1.218+.
- **`skills:`** (on agent definitions): When building a subagent (in `.claude/agents/`), you can preload specific skills into it via the `skills:` frontmatter field. The full content of each listed skill gets injected at startup — the subagent doesn't need to discover them.
- **`compatibility`**: Environment requirements (1-500 characters). Use to indicate required platform, system packages, or network access.
- **`license`**: Use if making the skill open source (e.g., MIT, Apache-2.0).
- **`metadata`**: Custom key-value pairs. Recommended: `author` and `version`.

### Forbidden in Frontmatter
- XML angle brackets (< >)
- Skills with "claude" or "anthropic" in name (reserved)

### No README.md
Don't include README.md inside the skill folder. All documentation goes in SKILL.md or references/. (A repo-level README for human users is separate.)

### SKILL.md Size
- Keep under 500 lines (~5,000 words) — a *readability* rule, inherited from Anthropic's guide. It is **not** the compaction budget: a file can sit comfortably inside the line rule and still be **2× the 19,900-character limit** below, because line count says nothing about line length. Check both.
- Move detailed docs to references/
- Link to references instead of inlining

**Why the limit is mechanical, not stylistic:** after auto-compaction, Claude re-attaches the most recent invocation of each skill, keeping the **first 5,000 tokens of each** under a **combined 25,000-token** budget, most-recent-first. So everything past ~5,000 tokens in a SKILL.md is the part a compacted session silently loses — and it's the tail, not the part you'd choose to drop. Put the load-bearing instructions early and push detail into `references/`, which is re-read on demand rather than truncated.

**The budget is characters, not tokens — measure it with `wc -m`.** The cap is documented as "5,000 tokens," but the runtime sizes a skill's content with a character heuristic rather than a tokenizer — `Math.round(chars / 4)` (**derived**: the truncator slices to `tokens × 4`, which implies the 4-chars-per-token model, but the size function itself could not be resolved in the bundle). Both figures below are therefore derived arithmetic, not literals you can grep for. The effective per-skill limit is:

| Documented | What the runtime actually enforces |
|---|---|
| 5,000 tokens per skill | **19,900 characters** (5,000 × 4, minus the 100-char truncation marker — 98 visible characters plus two leading newlines) |
| 25,000 tokens combined | **100,000 characters** across all invoked skills |

*Provenance, because these are numbers a reader should be able to re-check rather than trust: the
5,000 and 25,000 caps are hardcoded literals with no context-window scaling, read first-party from
the Claude Code bundle and unchanged across **2.1.222, 2.1.246 and 2.1.247** — three builds, three
different minified binding names, identical values. The character figures are derived from them
(`cap × 4`, minus the 100-character truncation marker for the per-skill row); neither appears as a
literal anywhere, so grepping for `19900` will find nothing. The `× 4` divisor is itself derived: it
follows from the truncator's own arithmetic, but the function that sizes the content could not be
resolved in the bundle, so treat it as a well-supported inference rather than a verified constant.*

```bash
wc -m SKILL.md          # characters — the unit that matters
# 19,900 or less survives compaction. Note: wc -c gives BYTES, which over-counts
# any file containing em-dashes or other multi-byte characters.
```

**Do not measure this with a real tokenizer.** `count_tokens` answers a different question, and the two units diverge widely on technical markdown — one file measured for this guide came to 13,388 real tokens against 39,696 characters, roughly 2.95 chars/token rather than 4. It is the *character* figure the compaction budget compares against, so a tokenizer reading is not wrong, just irrelevant here — and on technical markdown (~3 chars/token) relying on it overstates the overage by ~35%, erring toward a false red. Prose-heavy content above 4 chars/token would err the other way — which is the reason to measure characters rather than reason about the ratio at all.

**Two ways a skill loses content for the rest of a session, neither documented publicly. Both are conditional — the condition is stated with each:**

1. **Truncation is written back to the registry.** When a skill is truncated at re-attachment, the shortened text *replaces* the stored copy, so a second compaction in the same session cannot recover the tail. The file on disk is untouched, so a `Read` still recovers it; nothing else will. **Condition:** the write-back is skipped when the skill's content is already present in the conversation body — in that case the stored copy survives intact and the skill is simply omitted from that pass.
2. **Combined-cap overflow zeroes a skill outright.** Re-attachment packs skills most-recently-invoked first against the combined budget. A skill that doesn't fit has its stored content set to **empty**, and because a zeroed skill is skipped on sight it stays dropped for the rest of the session. **Condition:** the same one — a skill whose content is already in the conversation body is omitted rather than zeroed. Separately, a skill already carried as an attachment is skipped entirely: not re-attached, not truncated, not zeroed.

**The combined budget is consumed by post-truncation sizes**, so a large skill contributes its *capped* 5,000 tokens to the 25,000 total, not its full length. Read that together with the most-recently-invoked-first ordering, because the two only make sense as a pair: more skills fit than you would guess, so the combined cap bites later and less predictably than the per-skill one — and since eviction is least-recently-invoked-first, **the skill that vanishes is rarely the big one.** An author reasoning about size alone will look in the wrong place when a skill goes missing.

Practical consequence: if a skill exceeds the cap, front-load whatever must survive, and state early in the file that the reader should re-read it from disk if a later section appears to be missing. If a skill is over budget, the fix is to move whole phases into `references/` — not to trim prose, which rarely recovers enough.

---

## Advanced Skill Authoring Features

### Dynamic Context Injection (DCI)

Skills can inject dynamic, runtime-generated content into their instructions using the `` !`command` `` syntax. When Claude loads a SKILL.md and encounters a line like:

```
!`git log --oneline -5`
```

It runs the command at skill activation time and inlines the output into the skill body. This is powerful for skills that need fresh context — e.g., recent commits, current branch, running services, or environment variables. The command must be on its own line. Use sparingly — every injected command adds latency to skill loading.

### Path Variables

Skills have access to built-in path variables that resolve at runtime:

- **`${CLAUDE_SKILL_DIR}`** — resolves to the skill's own directory. Use this to reference bundled scripts, config files, and reference docs without hardcoding paths.
- **`${CLAUDE_PLUGIN_ROOT}`** — resolves to the root of the plugin containing this skill. Useful when multiple skills in a plugin share resources.
- **`${CLAUDE_PLUGIN_DATA}`** — a stable data directory per plugin that persists across skill upgrades. Use this for any data that should survive version bumps (logs, user config, caches).
- **`${CLAUDE_SESSION_ID}`** — the current session identifier. Useful for creating session-specific temp files or logs.

Example in SKILL.md:
```
Read the API reference at ${CLAUDE_SKILL_DIR}/references/api.md before making any calls.
Save persistent data to ${CLAUDE_PLUGIN_DATA}/history.json.
```

### Argument Substitution

Skills invoked via slash command can accept arguments. Use these placeholders in SKILL.md:

- **`$ARGUMENTS`** — the full argument string after the slash command
- **`$0`** through **`$9`** — positional arguments (space-delimited)

Pair with the **`argument-hint`** frontmatter field to show users what to type:

```yaml
---
name: deploy
description: Deploy a service to production.
argument-hint: <service-name> [environment]
---

Deploy the service "$0" to the "$1" environment (default: staging).
```

When the user types `/deploy api-gateway production`, `$0` becomes `api-gateway` and `$1` becomes `production`.

### `user-invocable: false`

Set this frontmatter field to hide a skill from the slash command menu. The skill can still be triggered automatically by Claude's description matching or referenced by other skills. Use this for:

- Helper skills that other skills depend on but users shouldn't call directly
- Skills that should only activate contextually, never via explicit invocation
- Internal building blocks in a multi-skill plugin

```yaml
---
name: internal-formatter
description: Formats output for the reporting skill. Used internally.
user-invocable: false
---
```

### Relative Markdown Links for Progressive Disclosure

Instead of writing "Read `references/api.md` for details", you can use standard markdown links:

```markdown
See the [API Reference](references/api.md) for endpoint details.
```

When Claude encounters these relative links in a skill, it knows to read the linked file if/when the information becomes relevant. This is a cleaner progressive disclosure mechanism than inline instructions telling Claude to read files — it lets the model decide when to follow the link based on the task at hand.

### Agent vs. Skill Frontmatter

Skills and agents (defined in `.claude/agents/`) share similar structure but have key differences in their frontmatter:

| Feature | Skill (SKILL.md) | Agent (.claude/agents/*.md) |
|---------|------------------|----------------------------|
| Tool control | `allowed-tools` (grant, no prompt) + `disallowed-tools` (denylist) | `disallowed-tools` (denylist) |
| Auto-trigger | Default on; `disable-model-invocation: true` to disable | N/A — agents are always explicitly invoked |
| Effort | Not applicable | `effort: low/medium/high` — controls thinking depth |
| Turn limit | Not applicable | `max-turns: N` — caps the agent's turn count |
| Skill preloading | Not applicable | `skills: [skill-a, skill-b]` — injects full skill content at startup |

Key takeaway: skills are designed for reuse and auto-discovery; agents are designed for scoped, explicit tasks. If you're building something that should fire automatically based on context, make it a skill. If it's a focused task the user will always invoke deliberately (like a code reviewer or test runner), consider an agent.

---

## Runtime Mechanics & Gotchas (Claude Code)

Everything in this section is Claude-specific (observed from Claude Code 2.1.222). Other agentskills.io hosts have their own runtime behaviors. If your skill must work across hosts, design against the portable spec first, treat these mechanics as bonus behavior you can lean into only when you know the target is Claude.

### Shell substitution (`` !`cmd` ``) — failure modes

Claude Code supports inline shell substitution in skill bodies. Authors should know:

- **CWD is the project working directory, not `${CLAUDE_SKILL_DIR}`.** Scripts needing their own dir need `cd "$(dirname "$0")"` at the top.
- **Non-zero exit fails the skill invocation.** User sees the command and stderr.
- **Must appear at line start or after whitespace.** Mid-word backticks won't substitute.
- **State doesn't persist between `!` blocks.** Each is independent.
- **Shell substitution runs synchronously before the body is sent.** Long scripts stall the whole turn — consider `context: fork` for non-trivial work.

### MCP-bundled skills — Claude carve-outs

If the skill ships via an MCP server (vs. as a local skill or plugin):

- Shell substitution is **skipped entirely** — `` !`cmd` `` stays as literal text.
- `${CLAUDE_SKILL_DIR}` is **inert** and passes through unsubstituted.
- `shell.interpreter` is ignored.
- `${CLAUDE_SESSION_ID}` still works.
- **`hooks` and `allowed-tools` are parsed and then dropped** — the runtime logs "MCP-sourced skills cannot register hooks" / "cannot bypass permissions." An MCP-shipped skill cannot grant itself tool access.

### Shared-memory skills — a second carve-out

A skill loaded from shared memory is more heavily restricted than an MCP-shipped one: capability frontmatter (`allowed-tools`, `hooks`, `model`, `shell`) is ignored, inline shell (`` !`` commands) does not run, symlinked files are not loaded, and a `SKILL.md` over 128 KB is skipped entirely. If a skill must work in that context, it can rely on nothing but its own Markdown.

### `paths:` is gitignore syntax, not glob

Claude's public docs call `paths:` patterns "globs." The runtime uses the `ignore` npm package (gitignore syntax). `src/**` and `src/payments/**` work; `src/**.ts` does not. Activation is sticky per-session until `/clear`.

### `allowed-tools` grants permission — it does not request it (Claude)

`allowed-tools` lists tools Claude may use **without asking** during the turn that invokes the skill; the grant clears when the user sends their next message. It is a grant, not a restriction, and its presence does not itself produce a permission prompt. Some specifics worth knowing:

- **`${CLAUDE_SKILL_DIR}` inside an `allowed-tools` Bash rule** lets a skill run a bundled script with no permission prompt (2.1.129+).
- **`shell:`** selects an interpreter only — `bash` or `powershell` for `` !``-command blocks. It has no permission semantics at all.
- **`disallowed-tools`** is the denylist counterpart: it *removes* tools while the skill is active.
- **The one real gate is workspace trust, and it is per folder, not per invocation.** For a skill in a project's `.claude/skills/`, its capability frontmatter (`allowed-tools`, `hooks`) takes effect only after the trust dialog has been accepted for that folder — the same model as `.claude/settings.json` rules. Accepting it once covers every later invocation.
- **Therefore: review project skills before trusting a repository.** A skill can grant itself broad tool access, and trusting the folder is what activates that grant.

Unknown/custom frontmatter fields are dropped by the parser — they don't prompt and they don't do anything.

### Skill content lifecycle (Claude)

Two different lifetimes, easy to conflate:

- **The skill's content is sticky.** An invoked `SKILL.md` enters the conversation once and **stays for the session**. Re-invoking with identical rendered content adds a note, not a second copy (2.1.202+). So a skill cannot "re-read itself" to refresh anything — design instructions to be read once.
- **The `allowed-tools` grant is not.** It covers the invoking turn and clears on the user's next message. A long multi-turn workflow cannot lean on a grant from turn one.
- **`background: false`** — with `context: fork`, waits for the subagent's result inside the invoking turn instead of backgrounding it. Use when the skill's next step needs the result. Requires 2.1.218+.

### Live reload — chokidar depth limit

Claude's file watcher scans the skills dir at **depth 2**. `<dir>/<skill-name>/SKILL.md` reloads live; `<dir>/<group>/<skill-name>/SKILL.md` (three levels deep) does not. Don't nest skills two levels deep if you want live reload.

### Skill name collisions — first wins silently

On Claude, priority chain is: bundled → built-in plugins → policy/managed → user (`~/.claude/skills/`) → project (`.claude/skills/` walking up from CWD) → `--add-dir` → legacy `.claude/commands/` → plugin skills → MCP skills. Loser is dropped silently (no warning). If a project skill won't load on Claude, check for a same-named user-level skill.

### Frontmatter fields to avoid

- `progressMessage` — no parser, render path drops it. Dead code as of Claude Code 2.1.222.
- Any custom/unknown field on Claude — silently dropped.

### SKILL.md filename — case matters on Linux/CI

Must be exactly `SKILL.md` (uppercase) in `.claude/skills/<name>/`. `Skill.md` works on macOS's case-insensitive filesystem but fails silently on Linux/CI. The portable spec also requires uppercase `SKILL.md`.

---

## Troubleshooting Guide

### Skill Doesn't Trigger
**Symptom:** Skill never loads automatically.

Quick checklist:
- Is description too generic? ("Helps with projects" won't work)
- Does it include trigger phrases users would actually say?
- Does it mention relevant file types if applicable?

**Debugging approach:** Ask Claude: "When would you use the [skill name] skill?" Claude will quote the description back. Adjust based on what's missing.

### Skill Triggers Too Often
**Symptom:** Skill loads for unrelated queries.

Solutions:
1. Add negative triggers: `"Do NOT use for simple data exploration (use data-viz skill instead)."`
2. Be more specific: `"Processes PDF legal documents for contract review"` instead of `"Processes documents"`
3. Clarify scope: `"Use specifically for online payment workflows, not for general financial queries."`

### A Skill's Description Disappears From the Listing (Claude Budget Overflow)
**Symptom:** On Claude Code, a skill still appears by name but its description is gone, and Claude stops consulting a skill it used last month — while other skills keep their descriptions in the same listing. (Specific to Claude; non-Claude hosts have their own discovery mechanisms.)

**Cause:** The listing shares one character budget across all installed skills — `contextWindow × 4 × skillListingBudgetFraction`, fraction default `0.01`, so ~8,000 chars at 200 K and ~40,000 at 1 M. On overflow, Claude keeps full descriptions for the skills ranked highest by recency-weighted usage and renders the rest as name-only. Degradation is **per skill and ordered**, not simultaneous: full and name-only entries coexist in the same listing, and the skills you haven't invoked recently are the ones that lose their text.

**Solutions:**
1. Run `/doctor` — it estimates the listing's cost and names the biggest contributors. `/context`'s Skills row reports the post-budget size.
2. Trim the biggest contributors at the source. Aim well below the 1,536-char per-entry default.
3. Disable skills you don't use (`/skills`), or set `skillOverrides: {<skill>: name-only}` for the ones you only ever invoke by slash command — a protected `name-only` skill stops competing for budget entirely.
4. Raise `skillListingBudgetFraction` in settings (or `SLASH_COMMAND_TOOL_CHAR_BUDGET` as an env override) if the listing genuinely needs to be bigger.
5. Prevention: run this skill's description optimizer (`scripts/run_loop.py`) — it's length-aware and won't drift into bloated descriptions. Pass `--target-length` for a tighter target.

### Instructions Not Followed
**Symptom:** Skill loads but Claude doesn't follow instructions.

Common causes:
1. **Instructions too verbose** — Keep concise, use bullet points, move detail to references
2. **Instructions buried** — Put critical instructions at the top, use ## Important or ## Critical headers
3. **Ambiguous language** — Replace "validate things properly" with specific checks
4. **Model "laziness"** — Add explicit encouragement for thoroughness

### Large Context Issues
**Symptom:** Skill seems slow or responses degraded.

Solutions:
1. Optimize SKILL.md size (move docs to references/, keep under 5,000 words)
2. Evaluate if you have too many skills enabled (20-50 simultaneously can degrade)

---

## Quick Checklist

### Before You Start
- [ ] Identified 2-3 concrete use cases
- [ ] Tools identified (built-in or MCP?)
- [ ] Reviewed this guide and example skills
- [ ] Planned folder structure

### During Development
- [ ] Folder named in kebab-case
- [ ] SKILL.md file exists (exact spelling)
- [ ] YAML frontmatter has --- delimiters
- [ ] name field: kebab-case, no spaces, no capitals
- [ ] description includes WHAT and WHEN
- [ ] No XML tags (< >) anywhere in frontmatter
- [ ] Instructions are clear and actionable
- [ ] Error handling included
- [ ] Examples provided
- [ ] References clearly linked

### Before Upload
- [ ] Tested triggering on obvious tasks
- [ ] Tested triggering on paraphrased requests
- [ ] Verified doesn't trigger on unrelated topics
- [ ] Functional tests pass
- [ ] Tool integration works (if applicable)
- [ ] Compressed as .zip file

### After Upload
- [ ] Test in real conversations
- [ ] Monitor for under/over-triggering
- [ ] Collect user feedback
- [ ] Iterate on description and instructions
- [ ] Update version in metadata
