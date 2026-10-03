# Validate, package and deliver

The full procedure behind SKILL.md's *Validate, package and deliver*, which keeps the commands you need in one pass. **`<this-skill-dir>`** below is the skill directory you resolved in SKILL.md (that section): the directory holding this skill's `scripts/`, as your shell sees it.

## Contents

- [Validate against the official checklist](#validate-against-the-official-checklist)
- [quick_validate](#quick_validate)
- [check_portability](#check_portability)
- [cowork-harness static checks](#cowork-harness-static-checks)
- [Package the skill](#package-the-skill)
- [What the .skill file is](#what-the-skill-file-is)
- [Deliver the .skill file](#deliver-the-skill-file)
- [Sending the .skill file is how the user saves it](#sending-the-skill-file-is-how-the-user-saves-it)

## Validate against the official checklist

Before packaging, run through the quick checklist from `references/official-guide-patterns.md` to catch common issues:

- [ ] Folder named in kebab-case
- [ ] SKILL.md file exists (exact spelling, case-sensitive)
- [ ] YAML frontmatter has `---` delimiters
- [ ] name field: kebab-case, no spaces, no capitals, matches folder name
- [ ] description includes WHAT the skill does and WHEN to use it
- [ ] No XML tags (< >) anywhere in frontmatter
- [ ] No "claude" or "anthropic" in the skill name
- [ ] Instructions are clear and actionable (not vague)
- [ ] Error handling included for likely failure modes
- [ ] If the skill produces a file for its user, the final step writes it to a stated path and then presents it (a path alone isn't delivery on every surface)
- [ ] Examples provided where helpful
- [ ] References clearly linked from SKILL.md
- [ ] SKILL.md stays under 19,900 characters (`wc -m`) — detailed content in references/, which is not compaction-capped (keep each file under the agent's whole-file read cap)
- [ ] No README.md inside the skill folder

## quick_validate

You can run `quick_validate` to check some of these automatically. **Run this and `check_portability` below from this skill's own directory** — the `python -m` module form resolves `scripts.` relative to the current directory, so it fails anywhere else. That directory is `<this-skill-dir>`; put the `cd` in the same command, since a shell's working directory may not carry between calls:

```bash
cd <this-skill-dir> && python -m scripts.quick_validate <abs-path-to-skill>
```

If the shell says the directory SKILL.md's `cd` line names does not exist, it sees these files under a different path (a local session's host loop on an older Desktop build; current builds rewrite the path). If that line shows the skill-directory variable unexpanded (it does when this skill is invoked before the conversation has started its cloud session, typically as its first message, and so does a re-read from disk after a compaction), the `cd` silently lands in the home directory. Either way, find the directory from the shell's side and `cd` to the one that holds `scripts/`:

```bash
find / -path '*skill-creator-plus/scripts/quick_validate.py' -print -quit 2>/dev/null
```

Never skip `check_portability` or hand-roll the `.skill` zip because the scripts seem unreachable — locate them.

## check_portability

Also run `cd <this-skill-dir> && python -m scripts.check_portability <abs-path-to-skill> --target <claude-code|claude-ai|cowork|all>` — a stdlib-only cross-runtime linter (no dependencies, runs in any environment). It flags constructs that break on the skill's target runtime: an over-cap `description`, subagent use (the Claude app's chat runtime typically has no sub-agent tool), `claude` CLI use (not on the chat runtime's PATH), browser/server assumptions (no display in a cloud or local session or the chat runtime), third-party Python imports outside the stack a cloud session preinstalls (each costs a `pip install` on every run, and a locked-down org can deny the egress that install needs), a `SKILL.md` over the 19,900-character post-compaction cap (`compaction-truncation-risk`), a workspace placed under a relative `outputs/` path, which a cloud or local session refuses, nests, or loses depending on where it runs (`outputs-prefix-relative`), a file written to a bare relative path, which lands where the user can't see it or is refused outside Claude Code (`relative-output-path`, advisory), a delivery tool named for only one kind of session (`delivery-tool-single-lane` — phrase delivery by outcome, naming no tool; naming both, capability-conditionally, is also acceptable and stays clean), the deliverable itself gated on a delivery tool's availability (`delivery-conditional-deliverable`), a description truncated in or dropped from the skill listing (`listing-entry-truncation`, `listing-desc-drop-risk`), a plugin's skills together over the combined post-compaction cap (`compaction-zeroing-risk`), and a plugin-level `bin/` that claude.ai rejects (`plugin-bin-directory`). Pass `--target` matching where the skill will run; `--strict` to gate.

## cowork-harness static checks

If `cowork-harness` is installed, also run its two token-free static checks — `cowork-harness lint-skill --strict <skill-dir>` and `cowork-harness analyze-skill --strict <skill-dir>`. They're cheap and safe on any skill, and catch runtime bugs the checklist can't (host-path leaks, interactive-artifact write-backs lost in a cloud or local session); their findings matter most for skills that will run in one. Optional — skip silently if the tool isn't installed. See `references/environments.md` § *Testing skills for cloud and local sessions with cowork-harness*.

## Package the skill

Package the final skill into a distributable `.skill` file, from this skill's own directory (located as in *quick_validate* above):

```bash
cd <this-skill-dir> && python -m scripts.package_skill <abs-path-to-skill-folder> [output-dir]
```

## What the .skill file is

**What the `.skill` file is:** a zip named `<skill-name>.skill` whose single top-level folder is the skill folder itself — `<skill-name>/SKILL.md`, `<skill-name>/scripts/…`, and so on — never files at the zip root. The folder name must equal the frontmatter `name` (validation runs first and refuses a mismatch), because installers key on that directory. Left out: `evals/` and `tests/` at the skill root, `__pycache__/`, `node_modules/`, `*.pyc`, `.DS_Store`, and every symlink (never followed, so nothing outside the folder is embedded); the script prints what it skipped.

`output-dir` is optional and defaults to the skill folder's parent, which is unwritable on a plugin or marketplace install — pass the destination explicitly, as an absolute path when a script will consume it.

## Deliver the .skill file

**Don't delete from the outputs directory.** A delete can be refused until the user approves it (always in a connected folder in a local session, and in the outputs directory on Desktop builds before 2.16120.0 and in bridge sessions), so a "remove the stale copy and re-copy" step — the natural way to sync two directories — can fail in production while succeeding in most test setups. Build once rather than staging a copy you have to refresh; if a file must change, overwrite it in place. Write the `.skill` file to a path you name in your reply — the workspace. (In a cloud or local session `package_skill.py` runs in the shell, so give it the shell form, `<abs-workspace>/…`; state the path in your reply in the file-tool form the user sees. Never a bare filename, never an unnamed location.) Then present it: scan your available tools for one whose description says it sends or presents files to the user, and call it — the file is not delivered until you do, and stating the path is not a substitute — unless your instructions explicitly say that writing into a named folder delivers the file and not to send it as well. Only if no such tool exists, the path you already stated is the presentation. See `references/environments.md` → *Delivering files to the user* for why this two-step rule exists and which tool serves which surface. Packaging itself works everywhere Python does — never make it conditional on a presentation tool.

## Sending the .skill file is how the user saves it

**Sending the `.skill` file is also how the user saves it.** Where the app renders a sent `.skill` as a card with a Save skill button (shown only when the user's organization allows skill creation), that button installs the whole package, scripts included, into the user's account — so sending it is never optional. If your tools also include one that saves a skill straight from the conversation, it carries `SKILL.md` alone: never use it instead of sending the file, and never for a skill that bundles scripts, references or assets. See `references/environments.md` → *Sandboxed sessions*.
