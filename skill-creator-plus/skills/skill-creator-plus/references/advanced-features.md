# Advanced Skill Authoring Features and Runtime Mechanics

Split out of `official-guide-patterns.md` (unchanged text) so each file stays under the agent's whole-file
read cap. Claude-specific features (Dynamic Context Injection, path variables, frontmatter fields, hooks,
MCP-bundled skills, compaction) and how Claude Code actually runs a skill.

## Contents

- Dynamic Context Injection (DCI)
- Path Variables
- Argument Substitution
- `user-invocable: false`
- Relative Markdown Links for Progressive Disclosure
- Agent vs. Skill Frontmatter
- Shell substitution (`` !`cmd` ``) — failure modes
- MCP-bundled skills — Claude carve-outs
- Shared-memory skills — a second carve-out
- `paths:` is gitignore syntax, not glob
- `allowed-tools` grants permission — it does not request it (Claude)
- Skill content lifecycle (Claude)
- Live reload — chokidar depth limit
- Skill name collisions — first wins silently
- Frontmatter fields to avoid
- SKILL.md filename — case matters on Linux/CI

## Advanced Skill Authoring Features

### Dynamic Context Injection (DCI)

Skills can inject dynamic, runtime-generated content into their instructions using the `` !`command` `` syntax. When Claude loads a SKILL.md and encounters a line like:

```
!`git log --oneline -5`
```

It runs the command at skill activation time and inlines the output into the skill body. This is powerful for skills that need fresh context — e.g., recent commits, current branch, running services, or environment variables. The command must be on its own line, and must be allowed: declare it in the skill's `allowed-tools` (here `Bash(git log:*)`). Use sparingly — every injected command adds latency to skill loading. This example suits Claude Code in a repository: in a cloud session the working directory is usually not a repository, `git log` exits non-zero, and a failing command can hang the conversation (see *Shell substitution (`` !`cmd` ``) — failure modes*).

### Path Variables

**To reach a bundled script, write `${CLAUDE_SKILL_DIR}/scripts/tool.py` in `SKILL.md`.** In Claude Code and a local session it is replaced with a real absolute path before the model sees it, so the model can hand that path straight to Bash. It arrives unexpanded when the skill is invoked before the conversation has started its cloud session (in the newer interface, typically as the first message), so pair it with a fallback that finds the file from the shell (stanza B of `assets/skill-script-invocation.md`). That is the whole answer for most skills; the rest of this section is edge cases, and you can skip to *Argument Substitution* unless you hit one.

The two that bite in practice: the token is **dead outside `SKILL.md`** — literal characters in a `references/*.md`, empty string in a shell — so a reference doc should name `scripts/tool.py` and let `SKILL.md` supply the base at the point of use. And if you want the model to invoke something as a *command* rather than a path, ship `bin/<name>` — but only for a CLI-installed plugin, since a top-level `bin/` makes a plugin unpublishable through claude.ai organization settings.

---

**These are not runtime variables. They are load-time string substitutions into definition text** — a find-and-replace over your `SKILL.md` body and frontmatter before the model sees it. Nothing exports them, so the moment a path leaves that file the token is dead. Read them that way and the limits below are consequences rather than trivia.

The operative rule is the one this guide already applies to workspaces: **resolve once where substitution works, then pass the resolved absolute string explicitly to everything downstream.** A shell, a `references/*.md`, and a sub-agent prompt all need the value, and none of them can re-derive it.

- **`${CLAUDE_SKILL_DIR}`** — the skill's own directory. The right way to reference bundled scripts *from `SKILL.md`*: write `python3 ${CLAUDE_SKILL_DIR}/scripts/tool.py` and the model receives a real absolute path it can then hand to Bash (except in the cloud case below). Braced form only, and it works in the `SKILL.md` body and in `allowed-tools` — nowhere else. In a `references/*.md` it arrives as literal characters; in a shell it expands to the **empty string**. Both fail silently.
- **`${CLAUDE_PLUGIN_ROOT}`** — the root of the plugin containing this skill, substituted **into definition text only**. See the three limits below before using it; two of them fail silently.
- **`${CLAUDE_PLUGIN_DATA}`** — a stable data directory per plugin that persists across skill upgrades. Use this for any data that should survive version bumps (logs, user config, caches).
- **`${CLAUDE_SESSION_ID}`** — the current session identifier. Useful for creating session-specific temp files or logs.

Example in SKILL.md:
```
Read the API reference at ${CLAUDE_SKILL_DIR}/references/api.md before making any calls.
Save persistent data to ${CLAUDE_PLUGIN_DATA}/history.json.
```

**Where each token is live**

| | `SKILL.md` body | `allowed-tools` | `commands/*.md` | `references/*.md` at runtime | Bash / sub-agent prompt |
|---|---|---|---|---|---|
| `${CLAUDE_SKILL_DIR}` | ✅ | ✅ | ❌ **literal** | ❌ literal | ❌ empty |
| `${CLAUDE_PLUGIN_ROOT}` | ✅ | ✅ | ✅ | ❌ literal | ❌ empty **or another plugin's root** |
| `${CLAUDE_PLUGIN_DATA}` | ✅ | ✅ | ✅ | ❌ literal | ❌ empty **or another plugin's data dir** |
| `${CLAUDE_SESSION_ID}` | ✅ | ❌ **not substituted** | ✅ | ❌ literal | ❌ empty |

The table describes Claude Code and local sessions. **A plugin skill invoked before the conversation has started its cloud session (in the newer interface, typically as the first message) arrives with `${CLAUDE_SKILL_DIR}` and `${CLAUDE_PLUGIN_DATA}` unexpanded in its `SKILL.md` body** (the other two tokens were not checked). Invoked later in the conversation, they arrive filled: the skill directory under `/root/.claude/plugins/synced/…`, and the data directory as `/root/.claude/plugins/data/<plugin>-synced`. A skill that may run in the cloud needs the shell-side fallback either way.

**The `commands/*.md` column is the trap: the answer is token-specific, not surface-specific.** A
command *is* a definition surface and substitution *does* happen there — just not for
`${CLAUDE_SKILL_DIR}`, whose two replacement sites are guarded on an `isSkillMode` flag that both
command load paths pass as false. So "does substitution happen in commands?" gets a truthful **yes**
and sends you the wrong way; only the per-token question answers it. Measured with one fixture
carrying both tokens on both surfaces, reading the delivered text rather than the model's report:

```
SKILL.md body       SKILL_SKILLDIR=/sessions/…/skills/ctl/scripts/y.py     substituted
                    SKILL_PLUGINROOT=/sessions/…/cmdprobe/scripts/y.py     substituted
commands/probe.md   CMD_SKILLDIR=${CLAUDE_SKILL_DIR}/scripts/y.py          LITERAL
                    CMD_PLUGINROOT=/sessions/…/cmdprobe/scripts/y.py       substituted
```

Every cell in the commands column is measured, not inferred. A second probe put four tokens in one
command body: `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_SESSION_ID}` and `${CLAUDE_PROJECT_DIR}` all came
back substituted, and only `${CLAUDE_SKILL_DIR}` came back literal — the guard is the sole
difference between them.

The `allowed-tools` column is a separate substitution pass from the body's, and it does not carry the same set — `${CLAUDE_SESSION_ID}` survives in a body and is passed through untouched in a permission rule.

**A skill usually carries its own location, but do not rely on it.** The runtime prepends `Base directory for this skill: <absolute path>` as the first line of the loaded content, and truncation is head-preserving, so that line survives *truncation* by construction — if a section was cut, the skill's absolute path is still the first thing in its own context. Four things break it:

- **The combined cap zeroes rather than truncates.** A skill that does not fit the 25,000-token budget has its stored content set to the empty string and is skipped on sight for the rest of the session. There is no first line because there is no content. This is the failure `compaction-zeroing-risk` exists to catch, and it is the one case where an author is told to re-read from disk and has nothing to read *from*.
- **It is the least-recently-invoked skill that gets zeroed**, since packing is most-recent-first — precisely the skill whose path you would need to recover.
- **The path may name a directory that no longer exists.** Plugin roots are version-stamped, so an ordinary update leaves the recorded path dangling even when the line itself survives intact.

- **It can name a directory a cloud session's shell doesn't have.** For a plugin skill invoked before the conversation has started its cloud session (in the newer interface, typically as the first message), it reads `/mnt/skills/plugins/<plugin>:<skill>`, which doesn't exist there; invoked later, it names the synced copy under `/root/.claude/plugins/synced/…`.

So treat the base-directory line as a first thing to try, not a guarantee. (It is also absent entirely for a single-file `commands/*.md`, which gets no such line at all.)

For anything the model invokes as a *command* rather than a path, ship `bin/<name>` and call it bare — on the CLI lane only; a top-level `bin/` is rejected outright by claude.ai organization distribution. See below for that restriction and for what to ship instead.

#### Where `${CLAUDE_PLUGIN_ROOT}` is and isn't substituted

"Resolves to the plugin root" is true in exactly one place. Two of the three limits below produce no error at all, which is how a skill ends up silently reading the wrong path.

1. ✅ **Definition text, at load.** A `SKILL.md` body, a command, a hook, an MCP server entry. The runtime rewrites the token before the text reaches the model. This works.
2. ❌ **Not in a `references/*.md` read at runtime.** Only the definition is rewritten. A reference doc opened with `Read` comes back as bytes from disk, so the token arrives **literally**, as the characters `${CLAUDE_PLUGIN_ROOT}`. Nothing warns you.
3. ❌ **Not part of the Bash tool's contract.** It is not one of the variables Claude Code exports for Bash. In a shell the token expands to the **empty string** — no error, no unbound-variable failure, just a path that silently loses its prefix and becomes relative.

   Worse than empty, it can be *set* and wrong: `CLAUDE_PLUGIN_ROOT` may be present in a shell while naming **a completely different plugin** than the one whose skill is running — typically alongside a `CLAUDE_PLUGIN_DATA` naming a third.

   The mechanism is `CLAUDE_ENV_FILE`, and it is designed behavior rather than a leak. The hook executor spawns each hook with `CLAUDE_PLUGIN_ROOT` set to **that hook's own** plugin root, and for four events — `Setup`, `SessionStart`, `CwdChanged`, `FileChanged` — also sets `CLAUDE_ENV_FILE`, documented in the CLI's own hook text as *"write bash exports there to apply env to subsequent BashTool commands."* Any such hook that dumps its whole environment therefore writes its own plugin's root into the session env, and every later Bash call inherits it. The scripts are concatenated in a deterministic order (`setup` → `sessionstart` → `cwdchanged` → `filechanged`, then by hook index), so the last export in that concatenation wins — which is some arbitrary *other* plugin, not yours.

   So a shell reading `$CLAUDE_PLUGIN_ROOT` may get nothing, or a confident, wrong, unrelated directory. Never trust it in a shell. The corollary for skill authors is the sharper one: **a variable being set in your shell is not evidence it was set for you.**

   *Lane caveat, because these two facts read as opposites: `CLAUDE_ENV_FILE` is a plain-CLI mechanism. In a local session the VM shell is sealed and hook exports do not cross the host/VM boundary, so "don't rely on a hook to export env for your shell commands" remains correct **there**. Neither fact generalizes to the other lane.*

Under a local session's host loop the substituted value is a **host** path. Current Desktop builds (since about September 2026) rewrite plugin and skill paths inside shell commands to the VM's mounts, so the token works in a shell command there; but the shell then prints the VM path, which the file tools refuse, so give the file tools the path from the skill text, never one the shell printed. `${CLAUDE_PLUGIN_DATA}` and the outputs path are not rewritten.

#### Braced or bare? The same token has three different form rules

There is no single answer, because three separate sites substitute this token and each accepts a different spelling. Getting this wrong fails silently in both directions — a bare token in a SKILL.md body is simply never replaced, and a braced token in an exec-form hook is passed through as literal text.

| Where | bare `$CLAUDE_PLUGIN_ROOT` | braced `${CLAUDE_PLUGIN_ROOT}` |
|---|---|---|
| SKILL.md / command **body text** | ❌ never substituted | ✅ substituted |
| `allowed-tools` permission-rule path prefix | ✅ | ✅ |
| Hook, **shell form** (no `args`) | ✅ | ✅ |
| Hook, **exec form** (`args` present) | ❌ not substituted | ✅ |
| `references/*.md` read at runtime | ❌ | ❌ — read as a file, never loaded as a definition |

The three regexes, from 2.1.251:

```js
// body text — braced only
function AG(e, t) { let o = e.replace(/\$\{CLAUDE_PLUGIN_ROOT\}/g, () => t.path); … }

// permission-rule path prefixes — either form
U = /^(?:\$CLAUDE_PLUGIN_ROOT|\$\{CLAUDE_PLUGIN_ROOT\})\//

// hook commands — the hook's own form decides
er.replace(hn.args === void 0
   ? /\$\{CLAUDE_PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT\b/g   // shell form: either
   : /\$\{CLAUDE_PLUGIN_ROOT\}/g,                          // exec form: braced only
   () => xr)
```

**When in doubt, brace it.** The braced form is accepted at every site; the bare form is accepted at only two of the four. There is no context where bare works and braced doesn't.

*There is no linter rule for this. Both a bare-form rule and a reference-file rule were designed and measured against the installed-plugin corpus; almost every occurrence of the token in a `references/*.md` is documentation **of** the token rather than a use of it, so the rules flag correct explanations of the hazard — including this section. Knowing the table beats scanning for it.*

#### For anything executable, ship `bin/` and call it bare — on the CLI lane only

**Lane restriction first, because it is fatal rather than degrading.** A plugin with a top-level
`bin/` **cannot be distributed through claude.ai organization settings at all.** Org marketplace
sync rejects that plugin (and syncs the rest of the marketplace); a direct upload under
*Organization settings → Plugins* is rejected with the same message, which begins `Plugin contains
a top-level bin/ directory`. The stated reason is that `bin/` entries are added to PATH on the CLI
but are not shown on the admin approval surface. The official marketplace docs scope the rule to
org distribution — GitHub and local CLI installs are unaffected — so this is a CLI-lane
optimisation, not a portable one. If the plugin might ever be published through an organization,
do not ship a top-level `bin/`.

**What to ship instead**, by what is doing the invoking:

- **A skill that shells out** — the case this guide is mostly about. Use the read path, then a
  filesystem search: write `python3 ${CLAUDE_SKILL_DIR}/scripts/<name>` in the `SKILL.md` body and
  fall back to locating the file from the shell's side when the two are different mounts or the token arrives unexpanded. That is
  stanza A/B of `assets/skill-script-invocation.md`, it needs no `bin/` and no PATH, and it is the
  form this repo's own harness scenarios exercise. The launcher was only ever an optimisation on
  top of it.
- **A hook, or an `mcpServers` entry** — `${CLAUDE_PLUGIN_ROOT}/scripts/<name>`, exactly as the
  docs say. The substitute is correct *here*, because these are definition-text surfaces where the
  token really is substituted.
- **Something the user types** — a `commands/*.md` slash command wrapping the script. The rejection
  message itself names hooks, commands and `mcpServers` as the sanctioned entry points.
- **Not a substitute: declaring `clis`.** On the org-remote lane the runtime materialises
  `bin/<key>` itself (see *Status* below) — but whether declaring `clis` clears claude.ai intake is
  untested here, so don't plan a distribution around it.

Two traps around that restriction:

- **`claude plugin validate` does not catch it.** Measured on 2.1.252 against a plugin carrying
  `bin/binprobe`: both `validate .` and `validate . --strict` reported only the unrelated `author`
  warning. The usual pre-flight gate returns green on a plugin that cannot be distributed, and the
  admin-side UI error is unhelpful too — Claude Desktop shows a generic "Marketplace sync failed.
  Check the repository URL and try again," with the real message only in the renderer log
  (`~/Library/Logs/Claude/claude.ai-web.log`, grep `MARKETPLACE_ERROR`). The one local gate is this
  skill's own linter: `cd <this-skill-dir> && python -m scripts.check_portability <skill> --target claude-ai` carries
  `plugin-bin-directory` (warning), which walks up to `.claude-plugin/plugin.json` and fires when
  that root holds a non-empty `bin/`.
- **The documented substitute is narrower than it reads.** The docs say to keep executables in
  `scripts/` and reference them as `${CLAUDE_PLUGIN_ROOT}/scripts/<name>`. That substitution happens
  in *definition text* — hooks, MCP server configs, a `SKILL.md` body — which is exactly the table
  above; a skill that shells out gets the empty string. Where a skill invokes a script from a shell
  rather than from a hooks/`mcpServers` config, the portable answer is the read-path-then-search
  resolver in `assets/skill-script-invocation.md`, not the documented one.

With that established: Claude Code puts **every enabled non-builtin plugin's `bin/` directory on the Bash tool's PATH**, and the entry is correct for that shell's own namespace in all three places — local CLI cache paths, local-session host-loop mounts, and cloud-session sync paths. So a scaffolded skill can ship `bin/<name>` and invoke it as a bare command:

```bash
my-plugin-tool --input foo      # resolved via PATH; no path crosses a namespace boundary
```

A launcher that needs its own plugin root can recover it from its own location rather than from an injected variable:

```sh
#!/bin/sh
PLUGIN_ROOT=$(cd "$(dirname "$0")/.." && pwd)
exec python3 "$PLUGIN_ROOT/scripts/tool.py" "$@"
```

This complements the "pass bundled scripts absolute paths" rule rather than replacing it: that rule is right, but it requires the caller to already *have* a correct absolute path, which is exactly what a shell cannot get from `${CLAUDE_PLUGIN_ROOT}`.

**Three caveats, all silent — construct, verify, fall back:**

- **Put `bin/` at the plugin root** — the directory containing `.claude-plugin/plugin.json`. That is what PATH receives. In a marketplace repo whose plugin lives in a subdirectory there are two candidate roots, and only the inner one counts. (A `bin/` elsewhere in such a repo is usually an ordinary project CLI and is fine where it is; this is about which directory PATH gets, not about tidying a repo.)

- **A PATH entry is not evidence the directory exists.** The builder maps every enabled non-builtin plugin to `<root>/bin` and filters only for shell metacharacters — there is no existence check, so the entry appears whether or not the directory is there. The consequence is a diagnostic that lies: `echo $PATH` shows your plugin listed and looks healthy, so "command not found" never means PATH is misconfigured — it means the file is missing, at the wrong root, or not executable. Check with `command -v`, not by reading PATH.

- **Commit the launcher executable.** The plugin mount is read-only in a cloud or local session, so a missing `+x` bit cannot be repaired at runtime.
- **A plugin path containing shell metacharacters is dropped from PATH silently** — the runtime filters those entries and logs a warning the model never sees. A plugin installed under a path with a `$`, a quote, or a backtick simply has no `bin/` on PATH.

*Status: verified on the local-install lane — the PATH entry is live (it resolves the moment the directory appears, with no reload) and source directories survive installation unaltered. On the org-remote lane the runtime writes into that directory too, and the rule is exact: a plugin root has a `bin/` **iff** its manifest declares `clis`, and the file dropped there is named for the declared key. So if you declare `clis: {foo: …}`, the runtime owns `bin/foo` — don't also ship a launcher by that name. Whether an author's differently-named launcher survives alongside the generated one is untested. The affordance appears to have no adopters yet, which is a reason to confirm a first use with `command -v <name>`, not a reason to doubt it.*

*Version note: the commonly-cited v2.1.91 origin for the PATH behavior is **unverified**. The CHANGELOG embedded in these binaries reaches back only to 2.1.220, so its absence there proves nothing either way.*

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

When the user types `/deploy api-gateway production`, `$0` becomes `api-gateway` and `$1` becomes `production`. In the Claude app, the user should pick the command from the `/` menu: one typed in full can be refused with "Unknown skill: <name>." before anything is sent, and no session starts.

In a cloud session, a skill invoked before the conversation has started its cloud session (typically its first message) receives `$ARGUMENTS` unfilled; the positional placeholders were not checked. Write the skill so it still works then.

On Claude Desktop, `argument-hint` also tells the model what to collect when the skill is invoked (seen in a local session, not in a cloud session); without it, the model infers from `SKILL.md`. In Claude Code it is a hint shown while typing.

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

- **Where it runs depends on the host, and on permissions.** Every command first goes through the shell tool's permission check. In Claude Code an allowed command runs, with the project working directory as CWD rather than `${CLAUDE_SKILL_DIR}` (scripts needing their own dir need `cd "$(dirname "$0")"` at the top), and its output is substituted. A command that is not allowed — one that touches a path outside the working directories, or uses `$(…)` the checker cannot analyse — makes the whole skill fail to load with "Shell command permission check failed", in the default permission mode; by the runtime's code, an uploaded skill's command stays literal in the CLI. In a local session the command is replaced with `[shell command execution disabled by policy]`. In a cloud session it reaches the model as literal text when the skill is invoked before the conversation has started its cloud session (in the newer interface, typically as the first message); after that, an allowed command runs and is substituted (a read inside the working directory did, and so did one the skill declared in `allowed-tools`), while one that needs approval, such as a write or a read outside the working directory, is not run: in auto mode it is rewritten as an instruction, `[run this first, exactly as written, and use its output: <command>]`, so it runs only if the model chooses to run it with a tool call, and in other modes the skill fails to load. A model asked to report such a line may print a plausible output it never computed; when testing, have the command produce a value nobody can guess and check it afterwards. Not with `uuidgen`, which the cloud container lacks: `cat /proc/sys/kernel/random/uuid`, declared in the skill's `allowed-tools` as `Bash(cat /proc/sys/kernel/random/uuid)`, ran there (untested without that entry). Don't make a skill depend on `` !`cmd` ``: keep it to reads inside the working directory or commands declared in `allowed-tools`; in the Claude app it can also arrive literal, disabled, or as an instruction to the model; and put anything load-bearing in a script the model runs explicitly.
- **A command that fails is worse than one that doesn't run.** Make every `` !`cmd` `` one that cannot exit non-zero in any environment the skill may run in. In Claude Code a failing command is reported to abort the skill load. In a cloud session, a command the skill declared in `allowed-tools` that then failed returned an error when the model invoked the skill ("Shell command failed for pattern …", seen once), and, when the user typed `/skill-name`, hung the conversation with no reply and no error ([anthropics/claude-code#99008](https://github.com/anthropics/claude-code/issues/99008)).
- **Must appear at line start or after whitespace.** Mid-word backticks won't substitute.
- **State doesn't persist between `!` blocks.** Each is independent.
- **Shell substitution runs synchronously before the body is sent.** Long scripts stall the whole turn — consider `context: fork` for non-trivial work, keeping in mind that a fork's output reaches the user only as the main model's rewrite of its final message (see *Additional Frontmatter Fields* in `references/official-guide-patterns.md`).

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
- **`background: false`** — with `context: fork`, waits for the subagent's result inside the invoking turn instead of backgrounding it. Use when the skill's next step needs the result. That result is the fork's last message only, relayed through the main model. Requires 2.1.218+.

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
