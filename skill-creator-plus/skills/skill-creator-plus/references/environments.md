Environment-specific adaptations of the core workflow. Read the section for the environment you're running in.

## Claude.ai-specific instructions

In Claude.ai, the core workflow is the same (draft → test → review → improve → repeat), but because Claude.ai doesn't have subagents, some mechanics change. Here's what to adapt:

**Running test cases**: No subagents means no parallel execution. For each test case, read the skill's SKILL.md, then follow its instructions to accomplish the test prompt yourself. Do them one at a time. This is less rigorous than independent subagents (you wrote the skill and you're also running it, so you have full context), but it's a useful sanity check — and the human review step compensates. Skip the baseline runs — just use the skill to complete the task as requested.

**Reviewing results**: If you can't open a browser (e.g., Claude.ai's VM has no display, or you're on a remote server), skip the browser reviewer entirely. Instead, present results directly in the conversation. For each test case, show the prompt and the output. If the output is a file the user needs to see (like a .docx or .xlsx), save it to the filesystem and tell them where it is so they can download and inspect it. Ask for feedback inline: "How does this look? Anything you'd change?"

**Benchmarking**: Skip the quantitative benchmarking — it relies on baseline comparisons which aren't meaningful without subagents. Focus on qualitative feedback from the user.

**The iteration loop**: Same as before — improve the skill, rerun the test cases, ask for feedback — just without the browser reviewer in the middle. You can still organize results into iteration directories on the filesystem if you have one.

**Description optimization**: This section requires the `claude` CLI tool (specifically `claude -p`) which is only available in Claude Code. Skip it if you're on Claude.ai.

**Blind comparison**: Requires subagents. Skip it.

**Packaging**: The `package_skill.py` script works anywhere with Python and a filesystem. On Claude.ai, you can run it and the user can download the resulting `.skill` file.

**Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. In this case:
- **Preserve the original name.** Note the skill's directory name and `name` frontmatter field -- use them unchanged. E.g., if the installed skill is `research-helper`, output `research-helper.skill` (not `research-helper-v2`).
- **Copy to a writeable location before editing.** The installed skill path may be read-only. Copy to `/tmp/skill-name/`, edit there, and package from the copy.
- **If packaging manually, stage in `/tmp/` first**, then copy to the output directory -- direct writes may fail due to permissions.

## Cowork-Specific Instructions

If you're in Cowork, the main things to know are:

- You have subagents, so the main workflow (spawn test cases in parallel, run baselines, grade, etc.) all works. (However, if you run into severe problems with timeouts, it's OK to run the test prompts in series rather than parallel.)
- You don't have a browser or display, so when generating the eval viewer, use `--static <output_path>` to write a standalone HTML file instead of starting a server. Then proffer a link that the user can click to open the HTML in their browser.
- Claude tends to skip the eval viewer in Cowork and jump straight to analyzing results itself. This defeats the purpose — the human needs to see the outputs and give feedback before you revise anything. Always run `generate_review.py` first (not your own custom HTML), then wait for the human to review. The eval viewer exists so the human can form their own opinion before you start making changes.
- **Feedback loop workaround (IMPORTANT):** In static mode there is no server, so the viewer cannot POST feedback to disk. When the user clicks "Submit All Reviews", the viewer shows the raw JSON in a copyable textarea. You (Claude) cannot read browser downloads, so the feedback loop requires one of these:
  1. The user **pastes the JSON** directly into the chat — you parse it inline. (Primary path; the viewer does not download any file.)
  2. The user **saves the JSON themselves** as `feedback.json` in the workspace folder you're using — you then read it with the Read tool.
  When you tell the user "come back and tell me you're done reviewing", also say: *"The viewer will show your feedback as JSON — please copy it and paste it here."* Don't assume a file will appear on its own.
- Packaging works — `package_skill.py` just needs Python and a filesystem.

- **Delivering files to the user — write to a stated path, then present it capability-conditionally.**
  Cowork's two lanes deliver differently, and treating them the same silently loses the file on one
  of them:
  - **Local Cowork**: the outputs directory is visible to the user, so writing the deliverable there
    and stating the path **completes delivery**.
  - **Remote cloud-container Cowork**: the session runs in an isolated sandbox "created when the
    session starts and destroyed when it ends" (Cowork architecture overview) — nothing persists or
    surfaces the outputs directory on its own. A file written there and never presented through a
    tool is **silently lost**; writing it is not delivery on this lane.

  Because a skill can't tell which lane it's on, teach both steps, always, in this order:
  1. **Write the deliverable to a stated path, unconditionally.** Never to cwd — in Cowork, cwd is a
     scratchpad the user can't see. This alone completes delivery on the local lane.
  2. **Then present it — scan for the tool, and call it if it exists.** Scan your available tools
     for one whose description says it sends or presents files to the user; that is the delivery
     tool on this surface, whatever it happens to be called. If one exists you **must** call it —
     the file is not delivered until you do, and stating the path is not a substitute. Only if no
     such tool exists, state the path. On the remote lane, this step **is** the delivery.

  Write step 2 generically in skills you author. The agent can already see its own tool list, so
  naming a tool adds nothing it doesn't know — while a hardcoded name is wrong on every surface that
  serves a different one, and rots when the names change. What prevents the silent loss is the
  *outcome* ("present it to the user"; "a path alone is not delivery everywhere"), not the mechanism.
  Be strict about the outcome and permissive about the tool — but never let "permissive about the
  tool" soften into "optional to call it when one exists."

  *Recognition aid, not authoring text — these exact names let a reading agent recognise the tool
  when it sees it in its own tool list; they are not meant to be transcribed into a skill's authored
  instructions: local Cowork serves `present_files`; remote Cowork and Claude Code have the native
  `SendUserFile`. Both are observed behaviour, not a published contract, and the split has already
  shifted once.*

  Never mention `device_commit_files` in authored skill text — it's Desktop plumbing that requires a
  `file_uuid` from a prior `SendUserFile` call; it is not a skill-level API.

  `check_portability.py` enforces this pattern with two rules: `delivery-tool-single-lane` fires
  when a skill names one delivery-tool family but not the other anywhere in its text, stranding the
  lane served by the missing one (the generic step-2 wording above names neither, which is clean, as
  is naming both — only naming exactly one strands a lane); `delivery-conditional-deliverable`
  fires when a line names a delivery tool alongside a skip/omit phrase governing the artifact itself
  (the real bug this guards against is gating *packaging* on tool availability, not presenting it
  conditionally). A file that genuinely must deviate from this pattern suppresses either rule with a
  file-scoped `portability-allow: file-delivery-tool` comment.

  *(Provenance, publicly checkable: `anthropics/claude-code` issue #50041 documents the Cowork-local
  delivery tool by exact name (`mcp__cowork__present_files`); issue #76344 documents the remote-lane
  tool (`SendUserFile`); issue #36438 documents the real upstream bug this guidance guards against —
  a skill gating its own packaging step on a delivery tool's availability. Anthropic's Cowork
  architecture overview (help center) describes the remote lane's session as sandboxed and
  ephemeral, which is why the write alone does not deliver there.)*

- Description optimization (`run_loop.py` / `run_eval.py`) should work in Cowork just fine since it uses `claude -p` via subprocess, not a browser, but please save it until you've fully finished making the skill and the user agrees it's in good shape.
- **Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. Follow the update guidance in the claude.ai section above.

## Testing Cowork-targeted skills with cowork-harness

skill-creator-plus can author skills for three runtimes — Claude Code, Claude Cowork, and Claude Chat. A skill that will run under **Cowork** faces a class of bug the quality evals cannot see: it only manifests under Cowork's real sandbox, default-deny egress, permission/AskUserQuestion protocol, and artifact-delivery rules (see "Cowork-Specific Instructions" above for the runtime constraints themselves). Examples: a `/sessions/...` host path leaking into model-visible text; an interactive HTML artifact whose relative `fetch`/form write-back is silently lost under Cowork (this is exactly the eval-viewer "says Saved, nothing reaches Claude" failure class this skill's own README documents); a denied egress; an unanswered permission gate; a deliverable that never reaches the user's workspace.

The companion tool `cowork-harness` (a separate CLI + skill, `npm i -g "cowork-harness@>=1.16.0"`) tests exactly this. It is **optional and Cowork-relevant only** — it does not judge output quality (that's this skill's job) and adds nothing for Claude Code / Claude Chat skills.

Cover the two tiers:

**1. Static checks (cheap, safe to run for any skill — no Docker, no token, seconds).** Two token-free commands catch the highest-value runtime bugs from source alone:
- `cowork-harness lint-skill --strict <skill-dir>` — flags Cowork host-loop footguns and unresolved `subagent_type` references (relevant here because skills can ship `agents/*.md` subagents).
- `cowork-harness analyze-skill --strict <skill-dir>` — flags `/sessions/...` host-path leaks AND interactive-artifact write-backs lost under Cowork, across SKILL.md + references/ + agents/ + any `.html/.js/.ts/.jsx/.tsx/.py` the skill bundles. Advisory findings (e.g. a write-back that correctly checks the response) do not fail; error findings (a write-back that shows a false "Saved") gate `--strict`.

These are read-only static scans; their findings only *matter* for a skill that will run under Cowork, but they are harmless to run on any skill. If `cowork-harness` is not installed, skip them silently — never make them a hard requirement. IMPORTANT install caveat: `npx cowork-harness@<ver>` can silently serve a stale cached CLI, so verify `cowork-harness --version` reports 1.16.x before trusting a run (this floor supports the scenario `lane:` key — added in 1.14.0 — and its token-free `record --dry-run --quiet` load-time validation, which catches a bad scenario config before any live spend).

**2. Live runtime testing (optional, heavier — Docker + a staged Claude Desktop agent binary + a token).** To actually execute the skill under Cowork's sandbox with scripted answers and assertions (egress, artifact delivery, cost budgets), author scenario YAMLs and run them at `container` fidelity. This is genuinely heavier and is not part of the default authoring loop. When a skill targets Cowork and the user wants this depth, explain what it checks in plain language, get their OK, then point them at this repo's own dogfood suite as the worked example: `harness/README.md`. Never run a live tier automatically, and never block packaging on it — a failed harness run is information to offer the user ("the skill leaked a host path; want me to fix it before packaging?"), not a gate.
