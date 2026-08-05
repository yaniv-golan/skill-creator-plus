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
  cassettes/                 # (no committed cassettes — see below; recorded on-demand / locally)
```

**No cassettes are committed — the CI gate is the static lane, not replay.**
A cassette records the skill's *own* behavior, so its staleness hash is tied to the skill's source.
skill-creator-plus is edited constantly, so a committed cassette goes stale on nearly every PR — and
re-recording needs Docker + a staged Claude Desktop agent + a token, a wall external contributors
can't clear. So the committed CI gate (`.github/workflows/harness.yml`) is the **token-free static
lane** (`lint-skill`, `analyze-skill`, scenario `lint`, `record --dry-run --quiet`), which is robust
to skill edits. Cassettes are
recorded **on demand / locally** (and in the deferred nightly live lane) — the recipe below still
applies; the resulting cassettes just aren't committed.
- `no-trigger` — cheap negative control; records + replays cleanly.
- `create-skill` — non-deterministic (LLM-authored gates) and bakes an un-scannable `.skill` artifact
  into the cassette; live-only by nature.
- `remote-delivery` — same non-determinism plus a `semantic_matches` LLM-judged assertion (see below);
  **live-only and never a PR gate**. CI only load-checks it via `record --dry-run` in the token-free
  static lane.

## Prerequisites

`cowork-harness` is a separate npm CLI (the Claude plugin ships only the skill, not the built CLI):

```bash
npm i -g "cowork-harness@>=1.16.0"
cowork-harness --version          # MUST report 1.16.x — `npx` can silently serve a stale cache
```

- **Static checks + `lint` + `replay`**: token-free, no Docker, no staged agent, no token.
- **Live `run` / `record`** (`container` fidelity): needs Docker **and** a staged Claude Desktop
  agent binary (or `COWORK_AGENT_BINARY`) **and** an Anthropic/OAuth token. Run
  `cowork-harness doctor --tier container` to check.

## The two lanes

### Token-free (runs anywhere, incl. CI — see `.github/workflows/harness.yml`)

```bash
# static skill checks (also run on the shipped skill by CI)
cowork-harness lint-skill   --strict skill-creator-plus/skills/skill-creator-plus
cowork-harness analyze-skill --strict skill-creator-plus/skills/skill-creator-plus

# scenario lint (catches silent false-greens: wrong-lane assertions, mixed-class items)
cowork-harness lint harness/scenarios/

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

The scenarios are **lint-clean but not yet recorded**. `create-skill.yaml` has **no `answers:`
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
  guard fails the run if a script throws `ModuleNotFoundError`. (The original rationale was measured
  wrong on 2026-08-05 — it assumed the base image carried no third-party packages and that egress
  denied installs outright; in fact the image ships a large Python stack and installing from PyPI
  works. The guard is kept because a module outside that stack still fails under an org that denies
  egress, and any Traceback is a regression regardless.) This class of bug is
  invisible in Claude Code (where the package is present) and to output-only evals — catching it is
  why this suite exists. (The scripts are stdlib-only for exactly this reason; see `check_portability`.)
- **Gates are stochastic** — the Capture-Intent questions and their option labels are LLM-authored
  and reworded every run, so scripted exact-label `answers:` hard-fail; hence `on_unanswered: llm`
  for `create-skill`.

## Remote-lane delivery contract (`remote-delivery.yaml`)

On Cowork's **remote** lane, a file written to disk and never surfaced through a tool is silently
lost — the session runs in a sandbox reclaimed at session end, and location delivers nothing there.
Every other check in this suite (and `check_portability`'s `delivery-*` rules, `analyze-skill`)
reasons about *authored text*; `remote-delivery.yaml` is the only check that observes the runtime
behavior of our own packaging step: it runs the flagship "create a skill, then package and give it
to me" prompt under `lane: remote` and asserts, via `semantic_matches`, that the agent either used a
tool to surface the resulting `.skill` file or explicitly acknowledged that no such tool exists on
this surface — never that it merely stated a filesystem path and called that delivery.

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

## Notes / landmines

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
