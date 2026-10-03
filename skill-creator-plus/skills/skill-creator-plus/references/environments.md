Environment-specific adaptations of the core workflow. Read every section whose condition your tool list and instructions meet — several can apply at once.

## Contents

- [Without sub-agents](#without-sub-agents)
- [Sandboxed sessions (cloud and local sessions, and the chat runtime)](#sandboxed-sessions-cloud-and-local-sessions-and-the-chat-runtime)
  - [Paths and workspace](#paths-and-workspace)
  - [Viewer and feedback](#viewer-and-feedback)
  - [Delivering files to the user](#delivering-files-to-the-user)
  - [Device tools and the user's computer](#device-tools-and-the-users-computer)
  - [Sub-agents](#sub-agents)
  - [Updating a skill](#updating-a-skill)
  - [Other](#other)
  - [Two skill listings in a local session](#two-skill-listings-in-a-local-session)
- [Telling runtimes apart](#telling-runtimes-apart)
- [Testing skills for cloud and local sessions with cowork-harness](#testing-skills-for-cloud-and-local-sessions-with-cowork-harness)

## Without sub-agents

Use this section when your tool list has no tool that dispatches a sub-agent — typically the Claude app's chat runtime, but check the tools, not the product. The core workflow is the same (draft → test → review → improve → repeat); some mechanics change. Here's what to adapt:

**Running test cases**: No subagents means no parallel execution. For each test case, read the skill's SKILL.md, then follow its instructions to accomplish the test prompt yourself. Do them one at a time. This is less rigorous than independent subagents (you wrote the skill and you're also running it, so you have full context), but it's a useful sanity check — and the human review step compensates. Skip the baseline runs — just use the skill to complete the task as requested.

**Reviewing results**: If you can't open a browser (e.g., a container or remote session), generate the static viewer (`--static`) and deliver it as in *Delivering files to the user* below. Only if no file can be delivered, present results directly in the conversation: for each test case, show the prompt and the output, and deliver any output file the user needs to see (like a .docx or .xlsx) the same way — a stated path alone is not delivery on every surface. Ask for feedback inline: "How does this look? Anything you'd change?"

**Benchmarking**: Skip the quantitative benchmarking — it relies on baseline comparisons which aren't meaningful without subagents. Focus on qualitative feedback from the user.

**The iteration loop**: Same as before — improve the skill, rerun the test cases, ask for feedback — just without the browser reviewer in the middle. You can still organize results into iteration directories on the filesystem if you have one.

**Description optimization**: This section requires the `claude` CLI (`claude -p`) on your shell's PATH (`command -v claude`). Skip it if it isn't there, or if you have no shell.

**Blind comparison**: Requires subagents. Skip it.

**Packaging**: The `package_skill.py` script works anywhere with Python and a filesystem. Run it, then deliver the resulting `.skill` file as described under *Delivering files to the user* below.

**Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. In this case:
- **Preserve the original name.** Note the skill's directory name and `name` frontmatter field -- use them unchanged. E.g., if the installed skill is `research-helper`, output `research-helper.skill` (not `research-helper-v2`). If it's a plugin your organization also ships under that name, the `/` menu shows two identical entries, and in local sessions both loaded the organization's copy; to test the user's copy, have them switch the organization's copy off for themselves under Customize.
- **Copy to a writeable location before editing.** The installed skill path may be read-only. Copy it into the directory your instructions designate for your work, by absolute path (`<abs-workspace>/<skill-name>/`), edit the copy there, and package from that copy with `package_skill.py`. Don't stage in `/tmp`, and don't assemble the `.skill` archive by hand.

## Sandboxed sessions (cloud and local sessions, and the chat runtime)

A **cloud session** or **local session** is the Claude app's task runtime, on Anthropic's servers or on the user's computer. It is not Claude Code on the web or the Claude Code CLI. A *sandboxed session* is either of them or the Claude app's chat runtime.

Use this section when your instructions say the user cannot see your working directory, name an outputs directory for the user's files, or describe sending files to the user — not a terminal on the user's own machine. That covers cloud and local sessions and the chat runtime. **Where to work is whatever your instructions designate, and it differs per session.** A local session names an outputs directory the user can see. A cloud session named only its working directory (`pwd`, e.g. `/home/claude`), which the user cannot see, plus a tool that sends files, in every live session checked. The client also has a per-session switch, read from its code and not seen live, under which the instructions name `/mnt/user-data/outputs` and say that writing there delivers the file. The directory can exist even when the instructions never mention it — then don't rely on it: deliver by what the instructions say, not by what is on disk. The chat runtime was seen naming `/mnt/user-data/outputs` (one observation). None of this tells you whether you have sub-agents. For current, dated runtime facts, human readers can see https://ccinternals.dev/cowork/ ; nothing in these instructions depends on fetching it. Anthropic documents that the org's network egress settings govern the session's shell and network, while web fetch and web search, MCP servers and Claude in Chrome sit outside them: web fetch reaches only URLs from search results or the conversation, and an admin can turn search off. The viewer and feedback bullets also apply to any session without a display.

In the newer interface a conversation starts as chat and creates a cloud session when it first needs a shell or files, and it ran in the cloud even with "Only on this computer" switched on. Where the interface still shows the Chat/Cowork picker, choosing Cowork starts a session with the task: it ran locally when that setting was on and in the cloud when it was off. Check where each task ran. Local tasks show: "Tasks on this computer are being deprecated … From October 6, you won't be able to start new ones. For new work on this computer, use Claude Code." For Pro and Max, Anthropic has announced: "On October 6, 2026, new Cowork tasks run in the cloud and the Only on your computer option in Settings > General will be removed. Tasks you already started on your computer stay there." From a cloud session, "When a task needs something on your computer, like a local file or your browser, Claude reaches it through the Claude Desktop app on that computer." Documented, not measured: Claude reaches only the folders the user has connected, and only while the app is open. If the app is closed, the session keeps running but can't reach local files. Local MCP servers work through the desktop app only. The device tool names below rest on one measured session. Facts below marked local apply only to local sessions. The main things to know are:

### Paths and workspace

- **Put the workspace where your instructions say to work, not beside the skill.** The skill directory is a read-only plugin mount here, so `<skill-name>-workspace/` cannot be its sibling. Measured twice (2026-08-06, both a full and a compaction-truncated skill): the agent silently falls back to the session scratchpad and writes the generated skill, its scripts, `evals.json`, fixtures and every eval output there — 26 and 41 files respectively, none of them reaching the user. In a cloud session the scratchpad is reclaimed at session end, so the user's new skill is **destroyed**; in a local session it merely stays invisible. A cloud session's whole sandbox, working directory included, is destroyed when the session ends (Cowork architecture overview), so nothing you build there survives unless you deliver it — package the skill and send the `.skill`, or commit it to a folder the user granted. Put the workspace in **the directory your instructions designate for your work**, by absolute path: `<skill-name>-workspace/` under it. In a local session that is the outputs directory, listed under "Additional working directories" — not the "Primary working directory", which on Desktop 2.7032.0 and later is a private app folder the agent may not read or write. In a cloud session it is usually the working directory itself, unless the instructions name an outputs directory. A relative path is the wrong form for a file-tool write: on current local Desktop it is refused by the agent's permission rules (measured on one machine), and in a cloud session it resolves against the working directory — right only when that is the designated place, and invisible to the user until delivered. The absolute form is correct regardless. (On older local Desktop a bare name did land in outputs; the absolute form is correct on both sides of that release.) Never put an `outputs/` segment in front of the workspace name either — see the prefix bullet below. To place the workspace in a folder the user has connected, in a local session use that folder's **absolute path on the user's machine** with the file tools; a relative `<folder>/…` does not reach it. In a cloud session connected to the user's desktop, that same path is **not** reachable by your file tools or shell — they act on the cloud container. A file-tool write to a path on the user's computer (their home folder, their Documents) still reports success: it creates that directory **inside the container**, and nothing reaches the user's computer. A path on the user's computer is an argument only to the device file tools (names containing `device_`; often deferred, so load them with ToolSearch), which list, stage and commit files into folders the user granted. If the task names a folder on the user's computer and none is granted yet, request access with the device folder-access tool, or ask the user; load the device tools with ToolSearch before concluding the computer is out of reach. To put a file into a granted folder, write it under the session's outputs folder and commit it from there, or send it to the user and commit the sent file. The commit tool does not take inline content, and it refuses to overwrite a file that changed on the user's side. A device shell tool, if present, runs in a local session on the user's computer and sees granted folders under its own mount (`$HOME/mnt/<folder>`), not at the Mac path. (Observed in one live session with the desktop connected.) Treat this choice as part of delivery rather than an implementation detail.
- **A path you hand to a script is not always a path you hand to a file tool.** Resolve the workspace once, in two named forms, and read both from your instructions rather than deriving either: **workspace (file tools)** is the absolute path of the directory your instructions designate for your work, plus the workspace; **workspace (shell)** is the same directory as your shell sees it. Where they differ is a local session's default host loop: the shell starts in the session root (`/sessions/<id>`), sees the outputs directory as `/sessions/<id>/mnt/outputs/`, and a connected folder as `/sessions/<id>/mnt/<folder>/`, while the file tools address the same directories by their paths on the user's machine and **reject every `/sessions/…` path**. Anything the shell writes outside `/sessions/<id>/mnt/` — including `/tmp` — stays inside the Linux environment and reaches neither the user nor your file tools. In a cloud session (the working directory, or `/mnt/user-data/outputs` when named), under the VM loop, and in plain Claude Code the two forms are the same string; still resolve and pass both. **So keep the identifier and the base apart:** name the run or workspace as a bare fragment that carries no prefix (`iteration-3/`, not `outputs/iteration-3/`), and let each family supply its own absolute base at the point of use. One directory, possibly two spellings; a single shared string is the thing that cannot be made correct everywhere. **A sub-agent gets both forms, labelled, copied verbatim** into its dispatch prompt — it uses the file-tools form with Read/Write/Edit and the shell form in any command, and never converts one into the other. **Pass bundled scripts absolute paths** — the shell tool's own documentation says the same. This applies to this skill's own scripts (`generate_review.py --static`, `run_loop.py --results-dir`, `package_skill.py`'s output directory) and to every script an authored skill bundles.
- **Say what a relative `outputs/…` path is relative to, or make it absolute.** A path whose first segment is `outputs/` resolves against whichever working directory the *reading* tool has. For a file-tool write it doubles to `outputs/outputs/…` on older local Desktop (hidden from the user's Working-folder panel), is refused on Desktop 2.7032.0 and later, and in a cloud session resolves against the working directory — outside `/mnt/user-data/outputs` where that is the delivery folder, and invisible to the user until sent. Under the local shell it resolves against the session root instead — invisible to the user *and* unreachable by the file tools, and it reports success. This bites hardest in text handed to a sub-agent, which has no author present to disambiguate. Two live examples from real skills: `RUN="outputs/$(date +%Y%m%d-%H%M%S)"` in a shell snippet, and a bare `outputs/<timestamp>/…` path in a dispatch prompt — one variable, both failure modes, opposite directions. Write the absolute path, or name the directory it is relative to in the same breath. *(No linter rule covers this: the hazard depends on a base the text does not state, and a regex for it flags the correct explanations of the bug as often as the bug — measured at roughly one true positive in eighteen across 263 installed skills. `outputs-prefix-relative` catches only the narrow workspace case, where the base is unambiguous.)* `check_portability` also flags the general form, a write to any bare relative file path, at advisory severity (`relative-output-path`); the fix is the same.
- **Locked-down orgs can run the whole agent inside the sandbox (the VM loop).** There the file tools and the shell share the sandbox's view: both address outputs as `/sessions/<id>/mnt/outputs/`, which is the only form under this loop, so the `/sessions/…` rejection above does not apply, and a relative file-tool write lands at the session root, invisible to the user. Inferred from the spawn code; not observed in a live locked-down org. The rule does not change: use the absolute path your instructions name.
- **Never rely on a working directory carrying between shell calls.** On a local session's host loop each call is independent — the shell tool's own description and the host-loop prompt section both say so — so a `cd` in one call is gone by the next and "cd there first, then use relative paths" silently breaks across a multi-step sequence. *Scope, stated because it is easy to over-generalise: that is a host-loop fact. Claude Code's own Bash tool documents the opposite for its main thread ("working directory persists between calls"), and under a sandboxed VM loop it persists — measured directly: the same two-call probe returns the `cd`-ed directory at VM-loop fidelity and the unchanged session root at host-loop, using a different shell tool in each case. So treat carryover as **unreliable**, not as reliably absent.* The rule is the same either way and needs no lane knowledge: **resolve the path once and pass it absolute.** An absolute path is correct on every surface; a `cd`-then-relative sequence is correct only where carryover happens to hold.
- **Always pass an explicit search path to Glob and Grep.** A pathless search means something different on every surface: locally it is re-anchored to the outputs directory, in Claude Code on the web it searches the repo, and in a cloud session it walks the container's whole home directory, including the agent's own session-credential files under `.claude/remote` — so it can put their names, and potentially their contents, into the conversation (observed in one cloud probe). Pass the workspace (file tools) path.
- **`Write`'s result echoes the path you gave it, not a resolved absolute path.** Don't capture an absolute path out of a Write result for a later step; it isn't there. A bundled script that resolves and prints its own output path is the only component that can report where the bytes actually went.

### Viewer and feedback

- A browser tool, if you have one, runs on the user's side: in a cloud session it can't reach a server you start or a file in your container, and in a local session that is untested. So when generating the eval viewer, use `--static <absolute-output-path>` to write a standalone HTML file instead of starting a server, then show it to the user as a page or deliver it as a file. To show it as a page, publish it with an Artifact tool if you have one, unless the outputs include spreadsheets (the viewer's spreadsheet preview loads a script from a source an Artifact page blocks) or the file is too large to publish; then deliver the file. There are two kinds, and a session has at most one: the `Artifact` tool publishes a page that appears in a panel beside the conversation, on the web as well as in the desktop app, and opens from its link on a phone; the older `create_artifact` family keeps the page in the Claude desktop app's Artifacts sidebar. Tell the user where to look, and that the viewer's Download links don't work in an Artifact (the app says "File downloads aren't available for this artifact."); the outputs still show in the page. Otherwise deliver the file by the two-step rule below; opened from there, binary downloads worked after the app asked the user to confirm, and text downloads need a base64 `data:` URI, which this viewer uses. Don't just give the user a link or a path: in a cloud session that delivers nothing. Either way, keep the paste-the-JSON feedback loop below: a rendered page has no channel back to you, so the conversation is the only return path, and it needs the user there.
- Claude tends to skip the eval viewer in these sessions and jump straight to analyzing results itself. This defeats the purpose — the human needs to see the outputs and give feedback before you revise anything. Always run `generate_review.py` first (not your own custom HTML), then wait for the human to review. The eval viewer exists so the human can form their own opinion before you start making changes.
- **Feedback loop workaround (IMPORTANT):** In static mode there is no server, so the viewer cannot POST feedback to disk. When the user clicks "Submit All Reviews", the viewer shows the raw JSON in a copyable textarea. You (Claude) cannot read browser downloads, so the feedback loop requires one of these:
  1. The user **pastes the JSON** directly into the chat — you parse it inline. (Primary path; the viewer does not download any file.)
  2. Where the user can see your workspace (a local session, Claude Code), the user **saves the JSON themselves** as `feedback.json` in the workspace folder you're using — you then read it with the Read tool.
  When you tell the user "come back and tell me you're done reviewing", also say: *"The viewer will show your feedback as JSON — please copy it and paste it here."* Don't assume a file will appear on its own.

### Delivering files to the user

- Packaging works — `package_skill.py` just needs Python and a filesystem.
- **Sending the `.skill` file is also how the user saves it.** In the Claude app a sent `.skill` renders as a card with a Save skill button; it installs the whole package — `SKILL.md`, scripts, references and assets — into the user's account, where it reaches their other sessions and the CLI. So package and send the file even when the user only wants the skill installed. Some sessions also give the model a tool that saves a skill from the conversation behind a card the user confirms. That route carries `SKILL.md` alone: a new skill saved that way has no scripts, references or assets, so never use it in place of sending the file, and never for a skill that bundles any of them. An update through it replaces only `SKILL.md` and keeps the skill's other files, which makes it the quick way to revise the instructions of a skill the user already has. Organization settings and plan tier decide whether a session gets that tool, so never depend on it. Skills belong to an organization: one saved or uploaded in one organization is not visible from a session in another.

- **Delivering files to the user — write to a stated path, then present it capability-conditionally.**
  Cloud and local sessions deliver differently, and treating them the same silently loses the file in
  one of them:
  - **Cloud session**: the session runs in an isolated sandbox "created when the
    session starts and destroyed when it ends" (Cowork architecture overview). Unless the
    instructions say otherwise, a file written there and never sent through a tool is **silently
    lost** — writing it is not delivery here. The client also supports sessions whose
    instructions say that writing under a named outputs directory delivers the file (read from its
    code, not seen live); there, that write is the delivery.
  - **Local session**: the outputs directory is visible to the user, so writing the deliverable there
    and stating the path **completes delivery**.

  Because a skill can't tell which kind of session it's in, teach both steps, always, in this order:
  1. **Write the deliverable to a stated path, unconditionally** — a path you name in your reply, not
     wherever the shell happens to be, because a tool-mediated write has its own working directory
     and an unnamed file is one the user can't find — see the path-split bullet above for which
     working directory each tool family actually gets. This alone completes delivery in a local session.
     A deliverable goes to **the directory your instructions designate**, by absolute path, in the
     form each tool family uses (see the two workspace forms above). Anywhere else is a temporary file by definition — including `/tmp`
     and any scratchpad the harness itself tells you to prefer, which may persist on disk and
     still never reach the user.
     *Where the file sits decides whether this step can work at all: in a local session a surfacing tool can only present files already under the outputs directory, the uploads directory, or a folder the user connected — if a shell command wrote it elsewhere in the Linux environment, copy it into one of those first, otherwise presentation fails outright, not just visibility. In every session, keep deliverables in the directory your instructions designate: an uploaded file's location differs by surface (find it from the message that announced it, never from a fixed directory), and it is a place to read from, not to present from.*

  2. **Then present it — scan for the tool, and call it if it exists.** Scan your available tools
     for one whose description says it sends or presents files to the user; that is the delivery
     tool on this surface, whatever it happens to be called. If one exists you **must** call it —
     the file is not delivered until you do, and stating the path is not a substitute. Nor is a link: in a
     cloud session a `computer://` link works only for a file this conversation wrote or sent, and any
     other — including one in a folder the user granted — shows as inert plain text, with no error. Only if no
     such tool exists, state the path. In a cloud session, this step **is** the delivery. One
     exception: when your instructions explicitly say that writing into a named folder delivers the
     file and not to send it as well, that write is the delivery, and sending it again only
     duplicates it.

  Write step 2 generically in skills you author. The agent can already see its own tool list, so
  naming a tool adds nothing it doesn't know — while a hardcoded name is wrong on every surface that
  serves a different one, and rots when the names change. What prevents the silent loss is the
  *outcome* ("present it to the user"; "a path alone is not delivery everywhere"), not the mechanism.
  Be strict about the outcome and permissive about the tool — but never let "permissive about the
  tool" soften into "optional to call it when one exists."

  *Recognition aid, not authoring text — these exact names let a reading agent recognise the tool
  when it sees it in its own tool list; they are not meant to be transcribed into a skill's authored
  instructions: local sessions and the chat runtime serve `present_files`; cloud sessions and Claude Code have the native
  `SendUserFile`. Both are observed behaviour, not a published contract, and the split has already
  shifted once. The same holds for file tools: the chat runtime's system prompt names them
  `create_file`, `view` and `str_replace` where this document says Write, Read and Edit. Route by
  what a tool does, not by its name.*

  In a cloud session the two tools deliver **different outcomes**, and the "present it" step above
  covers only the first:

  - *Surface it in the conversation* — the file appears in the chat and the user can open it there.
    The cloud session's `SendUserFile` returns a `file_uuid` for exactly this.
  - *Write it into a connected folder on the user's device* — the file lands on their real disk
    (mtime-guarded), and only inside a folder the user has granted. It prefers the `file_uuid` from
    the surfacing call, so the natural order is to run it *after* step 2 rather than instead of it;
    a file that was never surfaced must first be copied under `/mnt/user-data/outputs/`, the only
    other source it accepts. This is a real part of the cloud session's vocabulary, not internal
    plumbing: an agent given only "get the file to me" was observed choosing it unprompted, and the
    file arrived in the user's `~/Downloads`.

  As always, **name no tool in authored skill text** — the names differ per surface and rot. Phrase
  it by outcome instead: when the user asked for a file *on their machine* rather than a file *in the
  conversation*, then after surfacing it, if a tool exists that copies output files onto the user's
  device, call that too — surfacing alone does not put the file on their disk.

  `check_portability.py` also carries `outputs-prefix-relative` (warning, `cowork` target only): it fires on skill text that places a workspace directory under a relative `outputs/` prefix, which doubles into a hidden second outputs level on older local Desktop, is refused on Desktop 2.7032.0 and later, and is lost in a cloud session. Suppress per file with a `portability-allow: outputs-prefix` comment. It enforces the delivery pattern with two further rules: `delivery-tool-single-lane` fires
  when a skill names one delivery-tool family but not the other anywhere in its text, stranding the
  lane served by the missing one (the generic step-2 wording above names neither, which is clean, as
  is naming both — only naming exactly one strands a lane); `delivery-conditional-deliverable`
  fires when a line names a delivery tool alongside a skip/omit phrase governing the artifact itself
  (the real bug this guards against is gating *packaging* on tool availability, not presenting it
  conditionally). A file that genuinely must deviate from this pattern suppresses either rule with a
  file-scoped `portability-allow: file-delivery-tool` comment.

  *(Provenance, publicly checkable: `anthropics/claude-code` issue #50041 documents the local-session
  delivery tool by exact name (`mcp__cowork__present_files`); issue #76344 documents the cloud-session
  tool (`SendUserFile`); issue #36438 documents the real upstream bug this guidance guards against —
  a skill gating its own packaging step on a delivery tool's availability. Anthropic's Cowork
  architecture overview (help center) describes the cloud session as sandboxed and ephemeral,
  which is why the write alone does not deliver there.)*

- **Delivering words to the user — a script's stdout is not delivery for text.** The bullet above is
  the file case; this is its exact counterpart for prose, and it is lost the same silent way. In a
  terminal a Bash result renders inline under the call that produced it, so what a script prints is
  on the reader's screen. In a cloud or local session the app renders tool calls as **collapsed cards** — the reader sees *"ran 4
  commands"* and none of their output — so the only channel they read as prose is assistant text. A
  skill that computes its progress correctly, prints it correctly, and says nothing in its own voice
  has delivered that progress to the model and to nobody else. Worse, skills often *forbid* the one
  channel the reader does read, on the premise that the reader has already seen the tool output.
  **That premise is terminal-only.** Don't author it, and strip it out of a skill you are updating.
  Author as if nothing in the runtime will notice the silence and prompt you out of it.

  **Split on tense — the fix costs nothing from the anti-fabrication guarantee.** *The model may
  speak in the future tense; only a script may speak in the past tense.* A past-tense claim ("84
  clusters became 35 families") is the fakeable one — a model that skipped a stage describes having
  run it exactly as convincingly as one that ran it — so a script must produce it, counted from
  files at print time. A future-tense claim ("next I group what they connected") cannot be faked by
  announcing an intention: announce-then-skip leaves the next boundary line missing. The mechanism
  is a marker prefix on the reader-facing lines a script emits, plus one instruction — *repeat every
  marked line verbatim, marker stripped, nothing added, author nothing in between.* Mark **new**
  lines rather than retrofitting the marker onto existing operator output, which carries absolute
  paths and internal ids. Two traps worth inheriting rather than rediscovering: "repeat the lines
  worth repeating" hands the model exactly the editorial judgement the design exists to remove; and
  a marker is an **injection surface** wherever model-authored text is interpolated into a marked
  line — a sub-agent label containing a newline plus a forged marker is relayed with a script's
  authority — so sanitize where the value *enters*, not where the line is emitted, or the emitter's
  own byte-identity checks will flag every sanitized label as invented.

  **Don't design for mid-phase updates; they do not exist.** One assistant message can carry several
  `tool_use` blocks, and the model regains the floor only when *every* result in that batch returns.
  A phase implemented as one parallel dispatch is therefore structurally incapable of narrating from
  inside itself — text can appear before the batch or after all of it, nowhere in between — and
  finer granularity is bought only by splitting the batch and paying the wall-clock. So put the line
  at the phase **boundary**, and have the line before a long batch say how long the silence will be:
  predicted silence is a different experience from unexplained silence. *(This constrains where a
  line can go, not how often skills speak — most messages carry a single tool call. It is the
  fan-out phases that sit in the batched tail, which is exactly where the silences are longest.)*

  *(No linter rule covers this, and that is a measurement rather than an omission. The four
  recognisable phrasings of the bad premise return **zero** true positives across 411 installed
  `SKILL.md` files: three match nothing at all, and the fourth's five hits are two skills using
  "don't restate" for something else — a verification-methodology instruction, and a list of
  prohibition phrasings offered as an example of *bad* skill writing. Same bar that kept the general
  relative-`outputs/` case out of the linter. The symptom text being this rare is itself the finding:
  skills in this shape are not suppressing narration deliberately, they never considered the
  channel — which is a guidance problem, not a lint problem.)*

### Device tools and the user's computer

- **A skill that lives in a folder on the user's computer, from a cloud session.** You can reach it only inside a folder the user grants, and protected locations can't be granted: in one session `~/.claude` and `~/.claude/skills` were refused that way, so ask the user to send you a personal skill kept there. Bring the files in with the device stage tool and put your edits back with the device commit tool. Settle with the user where the result should live. A skill saved to their account (which sending the `.skill` file offers) loads in full in cloud and local sessions and in Claude Code, but only in the organization it was saved in. One kept in a project folder loads in Claude Code on that machine; A cloud or local session sees it only from a folder granted to a cloud session, and then only as a stub. Keep one of the two: Claude Code would see both copies, and how it chooses between them isn't documented.

### Sub-agents

- If your tool list has a sub-agent tool, the main workflow (spawn test cases in parallel, run baselines, grade, etc.) works; if not, *Without sub-agents* governs. (However, if you run into severe problems with timeouts, it's OK to run the test prompts in series rather than parallel.) One limit in a cloud session: sub-agents there cannot dispatch sub-agents of their own (the depth limit of one was measured in two cloud sessions; the refusal at that depth is read from the shipped agent, not exercised). So when the skill under test itself dispatches sub-agents, the executor running it has to flatten that work into its own context, and the results understate the skill. Evaluate such a skill in Claude Code (a local session also allows nesting, but new tasks cannot reliably be placed in one).
- **In a local session, a sub-agent cannot resolve a connected folder's mount name from its own prompt.** The per-folder mount table is built only in the main system prompt; a sub-agent's append carries the bare `/sessions/<id>/mnt/` prefix and nothing else. Since only an absolute path reaches a connected folder, a sub-agent asked to write into one must be **given the resolved path in its dispatch prompt**, in both labelled forms, since the shell and file-tool forms may differ. Otherwise it guesses a relative basename: on Desktop 2.7032.0 and later that write is refused, and on older Desktop it silently created a lookalike directory inside outputs instead of reaching the folder.

### Updating a skill

- **Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. Follow the update guidance in *Without sub-agents* above (its "Updating an existing skill" paragraph). It copies the skill into the designated workspace and not `/tmp`, which in a cloud or local session's shell is VM-private and reaches neither the user nor your file tools.

### Other

- Description optimization (`run_loop.py` / `run_eval.py`) runs `claude -p`, so it works here only if `command -v claude` finds the CLI in your shell; otherwise skip it, as in *Without sub-agents*. Either way, save it until you've fully finished making the skill and the user agrees it's in good shape.

### Two skill listings in a local session

A local session appears to show the model **two** skill listings at once, and they don't agree.
Observed in one controlled probe on the host loop (2026-08-05) plus the Desktop archive — treat it
as observed behaviour, not a published contract:

| | Desktop `<available_skills>` block | CLI `skill_listing` attachment |
|---|---|---|
| carries `when_to_use` | **no** | yes |
| budget-governed / truncated | no — verbatim, untruncated | yes (shared listing budget applies) |
| also adds | `<location>` + a read-only-cache note | — |

Two consequences when authoring for cloud or local sessions:

- **`when_to_use` is only half visible.** `description` reaches the model through both listings;
  `when_to_use` through only one. This is an independent, mechanism-level reason for the rule that
  `when_to_use` is never load-bearing — it is not just non-portable across hosts, it is partially
  invisible in Claude's own local sessions.
- **Cloud and local sessions read the account's skills, not your working copy.** A cloud session, scheduled
  routines included, runs in a container that can't see your Mac's files; a local session runs with
  its own configuration, not `~/.claude` (not tested directly). Both load the skills enabled for the
  user's claude.ai account, in the organization the session is in, plus enabled plugins. The Desktop
  syncs account skills on its own schedule (a new upload reached every surface within about a
  minute), and in a local session that synced copy is mounted read-only. So "I edited the skill
  locally" does not mean a cloud or local session sees the edit; the account-level skill has to be
  updated. Project skills in a folder the user connects are no substitute. Granted to a cloud
  session, a folder's `.claude/skills` arrive only as **stubs**: the frontmatter and a notice to run
  the skill on the user's device, with none of the body, so your scripts can't run in the cloud.
  This mode is server-gated and may change. A local session does not appear to load a connected
  folder's `.claude/skills` at all (read from the code, not traced end to end). A skill that must
  work in a cloud or local session belongs on the account or in a plugin, not in a project folder.

## Telling runtimes apart

Short answer: don't. Declare where a skill is meant to run with `--target` at authoring time, and at
run time branch on whether the capability you need is present — not on which product you are in.
Re-check if your tool list changes: a conversation that starts on the chat runtime can start a
cloud session partway through, when it needs a shell or files. On scheduled tasks, documented, not
measured: "Scheduled tasks run in the cloud, so they don't need your computer to be awake or the
desktop app open", but one that uses files on the user's computer needs the app open to reach them.
For Pro and Max, from 2026-10-06 "Your scheduled tasks move to the cloud too, including
ones that use files on your computer. Tasks that use files on your computer need the desktop app
open." What such a run does when the app is closed is untested. On plans and accounts the
2026-10-06 change hasn't reached, a Claude Desktop scheduled task set to run locally can change
place: a background sweep (server-switched, observed on one machine) moves a local task to
the cloud once it has run at least twice, unless a condition holds it back (for example an attached
Space, a working directory, or a custom cron schedule), so a skill tested only on local scheduled runs
can silently start running in the cloud. An
environment marker like `CLAUDE_CODE_IS_COWORK` misleads in both cloud and local sessions, for
different reasons. On the local host loop the agent and its shell are two contexts, and the marker set
on the agent does not reach the sealed shell, so a script there sees "not Cowork". In a cloud session
there is one context, but the marker is not set in it at all (observed in one probe). Either way it reports
"not Cowork" in precisely the configuration that needed detecting. For paths the rule is stronger
still: a script should not work out its own output location at all — the caller resolves it once
and passes an absolute path. See `references/official-guide-patterns.md` → *Declare at
authoring time, probe at run time* for the reasoning and the failure a guessing probe produces.

## Testing skills for cloud and local sessions with cowork-harness

skill-creator-plus can author skills for three runtimes — Claude Code, the Claude app's cloud and local sessions (Claude Cowork, now part of Claude for accounts that have moved over), and its chat runtime. A skill that will run in a **cloud or local session** faces a class of bug the quality evals cannot see: it only manifests under that session's real sandbox, org-configurable egress, permission/AskUserQuestion protocol, and artifact-delivery rules (see *Sandboxed sessions* above for the runtime constraints themselves). Examples: a `/sessions/...` host path leaking into model-visible text; an interactive HTML artifact whose relative `fetch`/form write-back is silently lost there (this is exactly the eval-viewer "says Saved, nothing reaches Claude" failure class this skill's own README documents); a denied egress; an unanswered permission gate; a deliverable that never reaches the user's workspace.

The companion tool `cowork-harness` (a separate CLI + skill, `npm i -g "cowork-harness@>=3.2.0"`) tests exactly this. It is **optional and relevant only to cloud and local sessions** — it does not judge output quality (that's this skill's job) and adds nothing for Claude Code or chat-runtime skills.

Cover the two tiers:

**1. Static checks (cheap, safe to run for any skill — no Docker, no token, seconds).** Two token-free commands catch the highest-value runtime bugs from source alone:
- `cowork-harness lint-skill --strict <skill-dir>` — flags local-session host-loop footguns and unresolved `subagent_type` references (relevant here because skills can ship `agents/*.md` subagents).
- `cowork-harness analyze-skill --strict <skill-dir>` — flags `/sessions/...` host-path leaks AND interactive-artifact write-backs lost in a cloud or local session, across SKILL.md + references/ + agents/ + any `.html/.js/.ts/.jsx/.tsx/.py` the skill bundles. Advisory findings (e.g. a write-back that correctly checks the response) do not fail; error findings (a write-back that shows a false "Saved") gate `--strict`.

These are read-only static scans; their findings only *matter* for a skill that will run in a cloud or local session, but they are harmless to run on any skill. If `cowork-harness` is not installed, skip them silently — never make them a hard requirement. IMPORTANT install caveat: `npx cowork-harness@<ver>` can silently serve a stale cached CLI, so verify `cowork-harness --version` reports 3.2.x before trusting a run. What this floor carries, in the order it will bite you: a session that does not pin `model:` inherits whatever model the local CLI happens to pick, and because the agent selects part of its **system prompt** by model capability, that moves the instructions the skill is tested against, not merely answer quality — 3.1.0 warns on it and the next major makes it an error, so pin `model:` in the session file. An omitted `fidelity:` likewise silently measures a skill against the VM-loop lane rather than the host-loop one production uses. The floor also carries the scenario `lane:` key, the token-free `record --dry-run --quiet` load-time validation that catches a bad scenario config before any live spend, and — from 3.2.0 — an `enum-value-invalid` lint ERROR, so a typo in a scenario enum (`result: succes`, `fidelity: bogus`) is caught by `lint` instead of linting clean and failing at load. The last two matter at tier 2 below, not here.

**2. Live runtime testing (optional, heavier — Docker + a staged Claude Desktop agent binary + a token).** To actually execute the skill under a cloud or local session's sandbox with scripted answers and assertions (egress, artifact delivery, cost budgets), author scenario YAMLs and run them at `container` fidelity. This is genuinely heavier and is not part of the default authoring loop. When a skill targets cloud or local sessions and the user wants this depth, explain what it checks in plain language, get their OK, then point them at this repo's own dogfood suite as the worked example: `harness/README.md`. Never run a live tier automatically, and never block packaging on it — a failed harness run is information to offer the user ("the skill leaked a host path; want me to fix it before packaging?"), not a gate.
