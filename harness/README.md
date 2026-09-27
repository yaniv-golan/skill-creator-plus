# harness/ — cowork-harness dogfood suite

This directory tests **skill-creator-plus's own skill** under Claude Cowork's runtime contract
(sandboxed agent, default-deny egress, the permission / AskUserQuestion protocol) using
[`cowork-harness`](https://github.com/yaniv-golan/cowork-harness). It is maintainer CI for *this
repo* — it is **not** part of the user-facing skill workflow and never runs for a user's skill.

It lives at the repo root, **outside** `skill-creator-plus/skills/skill-creator-plus/`, so it never
ships in the packaged `.skill` (same rule as eval definitions living outside the skill dir).

## Layout

```
harness/
  sessions/skill.yaml        # mounts this repo's plugin (skill-creator-plus@local)
  scenarios/
    no-trigger.yaml          # negative control: an unrelated prompt must NOT trigger the skill
    create-skill.yaml        # flagship: "create a skill" triggers + runs clean (LIVE-ONLY, see below)
    remote-delivery.yaml     # lane:remote delivery-contract guard (LIVE-ONLY, see below)
    shell-cwd-carryover.yaml # PROBE: does shell cwd persist between calls? (answer recorded in-file)
    script-path-guidance.yaml# guards the skill's own script-path answer (see its TIER NOTE)
    stanza-read-path.yaml    # assets/ stanza A end to end, container
    stanza-split-namespace.yaml # assets/ stanza B in the lane it exists for, hostloop
  sessions/fixture.yaml      # mounts fixtures/widget-fixture instead of this repo's plugin
  fixtures/widget-fixture/   # throwaway plugin built FROM assets/ — tests the templates we SHIP
  cassettes/                 # (no committed cassettes — see below; recorded on-demand / locally)
```

**`fixtures/widget-fixture/` tests the shipped templates, not this skill.** It is a plugin assembled
from `assets/skill-script-invocation.md` and `assets/plugin-bin-launcher.sh` exactly as an author
would, so a defect in those templates fails here. Three already have: a launcher pinned to the wrong
script directory, an error path killed by `set -e`, and a fallback tier that does not exist in the
lane it was written for. Attribution matters and is easy to overstate — only the third was found by
a harness RUN. The first two were found by exercising the fixture in a shell, after the harness
refused to stage it until it was committed. "The harness caught it" and "the harness made me build
something worth exercising" are different claims; this fixture earned the second one twice and the
first one once. Its `bin/wf` must stay mode `100755` in the index — `git ls-files -s` — or
the launcher cannot run once mounted read-only.

**Keep the fixture hook-free, in both spellings.** cowork-harness ≥3.0.0 refuses to spawn at
`protocol` when a staged plugin declares runnable hooks, unless the scenario sets
`allow_host_hooks: true` — because loading the plugin means the CLI executes those hooks as *native
host processes*, outside any sandbox. Hooks can be declared two ways, `hooks/hooks.json` **or** a
`hooks` key in `.claude-plugin/plugin.json`, and checking only the first is how you conclude
"no hooks" from a partial look — 3.0.0 shipped with the manifest spelling bypassing its own gate
(fixed upstream in `3c4d5fe`). Verified here: neither the fixture nor this repo's plugin declares
hooks in either form.

**Lane coverage for the `bin/`-on-PATH mechanism**, measured on that one fixture:

| lane | plugin `bin/` on the shell's PATH | read path resolves in the shell |
|---|---|---|
| container | **yes** (`/sessions/…/widget-fixture/bin`) | yes — so the launcher is never needed |
| microvm   | **yes** (same path shape) | yes — same, one command, first try |
| hostloop  | **no** (5 stock entries) | **no** — so the launcher is exactly what is missing |

That inversion is the finding: the launcher is on PATH where the read path already works, and absent
where it does not. `stanza-split-namespace.yaml` therefore asserts the *search* recovery, not the
launcher.

**microvm was dead here until cowork-harness 3.0.0**, and the fix is worth knowing because the
symptom named nothing: it resolved its agent binary by a path it derived itself instead of the shared
resolver, so a pin Claude Desktop had pruned surfaced as `env: 'claude': No such file or directory`,
exit 127. 3.0.0 routes it through `resolveAgentBinary`, restoring the existence check, the
pruned-binary fallback **and the sha verification** — microvm had been the one tier that executes the
ELF in a VM without verifying it. Re-measured after upgrading: the lane runs, and the L2 guest
firewall it uniquely provides is available again.

**One cassette is committed; the other two are live-only — the CI gate is mostly the static lane.**
A cassette records the skill's *own* behavior, so its staleness hash is tied to the skill's source.
skill-creator-plus is edited constantly, so a committed cassette goes stale on nearly every PR — and
re-recording needs Docker + a staged Claude Desktop agent + a token, a wall external contributors
can't clear. `no-trigger` is the exception and is committed: it is a cheap negative control with no
artifact, and over-triggering is a live risk every time the `description` changes — so a free replay
gate on every PR is worth its re-record cost. The other two stay live-only for the reasons below.

**What replay does NOT cover, and it is the important half.** Guards (`outputs-delete`, `host-path`)
run off the live run's scan, which a cassette does not carry — a replay reports them as `—`, not as
passing. The one real bug this suite has caught was a guard, not an assertion, so replay would have
shown eight green asserts and missed it. Treat the replay lane as regression cover for *content*,
and never as a substitute for a live run. So the committed CI gate (`.github/workflows/harness.yml`) is the **token-free static
lane** (`lint-skill`, `analyze-skill`, scenario `lint`, `record --dry-run --quiet`), which is robust
to skill edits. Cassettes are
recorded **on demand / locally** (and in the deferred nightly live lane) — the recipe below still
applies; the resulting cassettes just aren't committed.
- `no-trigger` — cheap negative control; records + replays cleanly.
- `create-skill` — non-deterministic (LLM-authored gates) and bakes an un-scannable `.skill` artifact
  into the cassette; live-only by nature.
- `shell-cwd-carryover` — a **probe, not a gate**: its assertions establish only that it ran and was not
  normalised, because persistence and independence are both legitimate outcomes and encoding one as
  "pass" would assert a conclusion nobody had. The measured answer (it persists at `container`, not at
  `hostloop`) is recorded in the file so it need not be re-purchased. Live-only; never a PR gate.
- `remote-delivery` — same non-determinism plus a `semantic_matches` LLM-judged assertion (see below);
  **live-only and never a PR gate**. CI only load-checks it via `record --dry-run` in the token-free
  static lane.

## Prerequisites

`cowork-harness` is a separate npm CLI (the Claude plugin ships only the skill, not the built CLI):

```bash
npm i -g "cowork-harness@>=3.10.0"   # needs Node >= 22
cowork-harness --version          # MUST report 3.10.x — `npx` can silently serve a stale cache
```

- **Static checks + `lint` + `replay`**: token-free, no Docker, no staged agent, no token.
- **Who can clear the staleness gate.** `verify-cassettes` runs unconditionally in CI, including on
  pull requests from forks, and a stale cassette is curable ONLY by re-recording — which needs the
  Docker + staged-agent + token setup below. So an outside contributor who edits anything under
  `skills/` that feeds the staleness hash gets a red gate they cannot clear themselves. That is
  expected: the maintainer re-records, the contributor does not. `staleness.hash_ignore` in
  `harness/sessions/skill.yaml` keeps `tests/` and `eval-viewer/` edits out of the hash so the
  common contributions do not trip it at all.
- **Live `run` / `record`** (`container` fidelity): needs Docker **and** a staged Claude Desktop
  agent binary (or `COWORK_AGENT_BINARY`) **and** an Anthropic/OAuth token. Run
  `cowork-harness doctor --tier container` to check.
- **If you ever add a host-inheriting scenario** (`protocol` / `hostloop`, or `cowork` resolving to
  hostloop), note two 1.18+ behaviours that do not affect today's suite — every scenario here is
  `fidelity: container`, which is tier-gated out of both. First, `record` **refuses before spending**
  to write such a recording into a repo-visible path. 3.2.0 states the refusal predicate where the
  refusal is explained rather than as an aside ~130 lines away, and it is a conjunction of three
  things: a host-inheriting tier **and** a repo-visible destination **and** nothing there yet — so an
  existing cassette is exempt and re-recording one is never refused. `harness/cassettes/` *is*
  repo-visible here (it holds a tracked `.gitkeep`). The destination judged is `--out` if given, else
  the default path **relative to the current working directory**, so previewing from a different
  directory asks about a different destination and can return the opposite verdict. Override
  deliberately with `--allow-host-inventory-fixture`; redirecting `--out` outside the repo is NOT a
  fix — the cassette stores its session/scenario references relative to its own directory, so one
  written outside the tree can never resolve them again. Second, `verify-cassettes` gains a `host-inventory` finding class
  that flags the recording machine's own MCP servers, agents, account fields and installed skill names
  frozen into the cassette — a real disclosure risk for a public repo, and not something `grep` or the
  text scanner can see.

## The two lanes

### Token-free (runs anywhere, incl. CI — see `.github/workflows/harness.yml`)

```bash
# static skill checks (also run on the shipped skill by CI)
cowork-harness lint-skill   --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness analyze-skill --strict skill-creator-plus/skills/skill-creator-plus

# scenario lint (catches silent false-greens: wrong-lane assertions, mixed-class items)
cowork-harness lint --strict --min-severity WARN harness/scenarios/

# real-loader load-check (lint only WARNS on an unknown key; this proves the suite actually loads)
cowork-harness record harness/scenarios/ --dry-run --quiet

# once cassettes are recorded:
cowork-harness verify-cassettes harness/cassettes   # PII + staleness (BLOCKING before commit)
cowork-harness replay harness/cassettes              # deterministic, token-free
# Run with NO allowlist flags — there are no sanctioned allowlist entries. Any finding is real and
# must be investigated/scrubbed before committing (public repo), never allowlisted away to force it.
```

### Live (maintainer only — needs Docker + staged agent + token)

```bash
cowork-harness doctor --tier container
cowork-harness run harness/scenarios/create-skill.yaml     # execute under the real sandbox
cowork-harness run harness/scenarios/remote-delivery.yaml  # remote-lane delivery-contract check (see below)
```

## Recording cassettes (the one maintainer step this suite still needs)

The scenarios are **lint-clean but not recorded** — no committed cassettes. *Recorded* and *run* differ: `create-skill.yaml` has been run live and passed, it simply has no cassette. `create-skill.yaml` has **no `answers:`
block at all** — the Capture Intent interview asks gates whose exact option labels are
model-decided and reworded every run, so it uses `on_unanswered: llm` instead of scripted labels
(see "What a live run checks" below). Run it live once to see the real gates before recording the
locking cassette:

```bash
# 1. Run once, keep the run dir
cowork-harness run harness/scenarios/create-skill.yaml --keep       # prints the run dir on stderr

# 2. Read the real gates + offered labels (token-free) — informational; not pasted into an
# `answers:` block, since the scenario deliberately has none (see above)
cowork-harness trace <run-dir> --view questions

# 3. Re-check assertions/answers against that run without re-paying (~1s)
cowork-harness verify-run <run-dir> harness/scenarios/create-skill.yaml

# 4. Commit the skill tree (real Cowork ships the committed tree), then record the locking cassette
cowork-harness record harness/scenarios/create-skill.yaml --out harness/cassettes/create-skill.cassette.json

# 5. Privacy + staleness gate BEFORE committing the cassette (public repo — blocking; no allowlist flags)
cowork-harness verify-cassettes harness/cassettes/create-skill.cassette.json
```

Then commit the cassette; the CI `replay` lane picks it up automatically.

## What a live run checks

Running the flagship scenario under `container` fidelity exercises real Cowork-runtime behavior that
Claude Code and output-only evals can't see:

- **Triggers and runs clean** — the skill activates on "create a skill…", produces a `SKILL.md` +
  packaged skill, with no host-path leak (`transcript_no_host_path`) and no egress surprises.
- **Bundled scripts run under the base image** — `create-skill.yaml`'s `tool_result_not_matches`
  guard fails the run if a script throws `ModuleNotFoundError`. The image ships a large Python stack
  and can install from PyPI, so most imports resolve — but a module outside that stack still fails
  under an org that denies egress, and any Traceback here is a regression whatever its cause. This
  class of bug is invisible in Claude Code (where the package is present) and to output-only evals —
  catching it is why this suite exists. (The scripts are stdlib-only so they never depend on the
  image's inventory; see `check_portability`.)
- **Gates are stochastic** — the Capture-Intent questions and their option labels are LLM-authored
  and reworded every run, so scripted exact-label `answers:` hard-fail; hence `on_unanswered: llm`
  for `create-skill`.

## Remote-lane delivery contract (`remote-delivery.yaml`)

On Cowork's **remote** lane, a file written to disk and never surfaced through a tool is silently
lost — the session runs in a sandbox reclaimed at session end, and location delivers nothing there.
Every other check in this suite (and `check_portability`'s `delivery-*` rules, `analyze-skill`)
reasons about *authored text*; `remote-delivery.yaml` is the only check that observes the runtime
behavior of our own packaging step: it runs the flagship "create a skill, then package and give it
to me" prompt under `lane: remote` and asserts, via `semantic_matches`, that the agent packaged the
skill and wrote the `.skill` file to an **explicitly stated, user-reachable location that it told the
user about** — rather than leaving it in a scratch directory or referring to it vaguely.

An earlier version of this paragraph described the rubric as grading whether the agent "used a tool
to surface the file, or acknowledged that no such tool exists." That shape is **unassertable**, and
cowork-harness 1.17.0 says so explicitly: the judged document is assistant text plus authored files,
so the judge cannot see tool calls on any lane — the first branch could never grade true regardless
of behaviour. The scenario's own inline comment carries the full reasoning.

It deliberately does **not** use `user_visible_artifact`: that key is rejected at load time on
`lane: remote`, because on that lane it could only ever report "cannot verify" (no `present_files` is
served there). The assertion is a `semantic_matches` rubric instead of a `transcript_matches` regex,
because this repo's own guidance tells the agent to name no delivery tool, and none is served on this
lane — so a correct run names no tool at all, which a name-matching regex would flag as red-on-correct.

**Live-only and never a PR gate** — same reasoning as `create-skill.yaml` (LLM-authored gates, a
binary `.skill` artifact) plus an LLM-judged `semantic_matches` assertion. CI only load-checks the
scenario file (`record --dry-run`); a human runs it on demand:

```bash
cowork-harness run harness/scenarios/remote-delivery.yaml
```

**All three scenarios have passed live**, but not with equal force. `create-skill.yaml` verifies the
local-lane delivery contract with *evidence* (`present_files_called`). `remote-delivery.yaml` passes
a *rubric* — on `lane: remote` nothing is delivered by location and the harness models no remote
delivery tool, so `delivery_unobservable` fires on every run and delivery there is unmeasured rather
than clean. Guards matter as much as assertions: a run can pass every assert and still fail on
`outputs-delete` or `host-path`, which is how this suite has actually earned its cost.

### Known coverage gap: script output paths

**A green run here does not certify that a bundled script's output reached the user.** In production
under host-loop Cowork, `mcp__workspace__bash` starts at the session root `/sessions/<id>`, while the
file tools take the outputs directory (as their cwd before Desktop 2.7032.0; from 2.7032.0 their cwd is
`/var/empty` and they refuse relative paths) — so a relative path written by a *script* lands somewhere
neither the user nor the file tools can reach, silently. No harness tier reproduces that split.
Measured, one run per tier (2026-08-27), `printf 'RELMARK\n' > rel.txt; pwd; readlink -f rel.txt`:

```
container : cwd = /sessions/<id>             -> PERSISTS to the run dir as session/rel.txt
hostloop  : cwd = /sessions/<id>/mnt/outputs -> mnt/outputs/rel.txt     [pre-fix harness; since changed]
```

`container` puts the write in the right *location* with the wrong *semantics*: it persists where
production discards it. This suite is container-only, so that is the row that applies to us.

**What a stray bash write can actually fake, precisely:** `containedPath` rejects anything resolving
to `..` or above the work root, so `file_exists`, `user_visible_artifact` and `computer_links_resolve`
cannot reach such a file at all. The exposure is `semantic_matches` and `no_lost_write_back`, which
grade the authored set. So the defensible claim is narrow: **a rubric like "the report was written"
grades TRUE on a file production would discard.** `remote-delivery.yaml` grades entirely via
`semantic_matches`, so it is the scenario this actually bites.

**The upstream fix has landed** (cowork-harness 2.4.0: `mcp__workspace__bash` now starts at the bare
session root at `fidelity: hostloop`, instead of collapsing it into `mnt/outputs`). The gap here is
now *ours*, not theirs: **every scenario in this suite is `fidelity: container`**, and the tier that
reproduces production's split is `hostloop`. Closing it means adding a hostloop scenario — which is a
real decision, not a config change, because `transcript_no_host_path` fails by design off container
and `no_scratchpad_leak` is container-only. Until such a scenario exists, do not read a green dogfood
as covering script paths.

## Notes / landmines

- **Read agent transcripts, not `audit.jsonl`, for any path-shaped comparison.** `audit.jsonl` is a
  translated projection that rewrites VM paths to host equivalents, so it will quietly corrupt a
  path claim. Use the transcripts under `.claude/projects/`.
- **A probe can be defeated by the model normalising the thing under test.** A post-fix verification
  appeared to show the fix had failed because the model had silently prepended
  `cd /sessions/.../mnt/outputs &&` to the command it was handed; it was caught only by re-checking
  the clean pre-fix runs. This happened four times in one investigation. Forbid `cd`, command
  chaining and absolute paths explicitly in the probe prompt, and read the command **actually sent**
  from `events.jsonl` rather than trusting the tool's output.

- `create-skill.yaml` uses `fidelity: container` — required for `transcript_no_host_path` (it fails
  by design on `protocol`/`hostloop`). A scenario using `no_scratchpad_leak` must also be `container`
  (`lint` errors on that key off-container); `present_files_called` is valid at `container` **or**
  `hostloop` (the harness serves `present_files` at both).
- Assert on artifacts/content, never `result: success` alone — success means "agent didn't error",
  not "task complete".
- On the token-free `replay` lane, live-only keys (`transcript_no_host_path`, `egress_*`) are skipped
  loudly, not evaluated — those are the reason a periodic live `run` matters. The nightly live lane is
  intentionally **deferred** (a self-hosted arm64 runner is real ops cost); see
  `docs/internal/cowork-harness-integration-plan.md`.
