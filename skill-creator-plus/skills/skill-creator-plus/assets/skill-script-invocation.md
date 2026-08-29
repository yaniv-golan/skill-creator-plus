# Script-invocation stanza — paste into an authored SKILL.md

Skills that bundle scripts keep inventing their own wording for "how do I run this", and most of
the inventions are wrong in a way that fails silently. Paste one of the two stanzas below into the
authored skill's `SKILL.md` instead. Replace `<script>` with a real name; replace `<cmd>` with the
launcher's name if you shipped one.

Both are written for the SKILL.md **body**, which is where the path token is substituted. Do not
move either into a `references/*.md` — a reference file is read from disk at runtime and the token
arrives as literal characters.

---

## A. No launcher (the default — use this unless you shipped `bin/`)

```markdown
**Running this skill's scripts.** Use the absolute path this file was loaded with:

    python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py [args]

Do not type `$CLAUDE_SKILL_DIR` into a shell command — it is a load-time text substitution, not an
environment variable, and expands to nothing in a shell. Read the resolved path out of this line
and pass it along verbatim, including to any sub-agent.
```

## B. Where the shell may not share the file tools' filesystem (Cowork host loop)

```markdown
**Running this skill's scripts.** Prefer the absolute path this file was loaded with:

    python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py [args]

If the shell reports that path missing, you are on a host where the shell and the file tools are
different mounts of the same content (Cowork's host loop). The file is there under a different
absolute path, so locate it from the SHELL's side and run what it finds:

    find / -path "*<skill-name>/scripts/<script>.py" -print -quit 2>/dev/null

Do not type `$CLAUDE_SKILL_DIR` or `$CLAUDE_PLUGIN_ROOT` into a shell command. Neither is
exported: the first expands to nothing, and the second may be set to a *different* plugin's
directory, so checking whether it is empty will not tell you it is wrong.
```

**A `bin/` launcher is an optimisation here, not the fallback.** If you ship one (see
`assets/plugin-bin-launcher.sh`), the skill may try `command -v <cmd>` before the search — but it
must not depend on it. Measured under Cowork host-loop: the workspace shell's `PATH` was eight
stock entries with **no plugin `bin/` at all**, so `command -v` found nothing and only the search
recovered. Install it as described in the launcher's header, confirm `<cmd> --list` names your
scripts, and still keep the search branch.

---

## If the skill will be packaged for other hosts

`${CLAUDE_SKILL_DIR}` is Claude-only. `skill-packager` strips it from non-Claude copies where a
relative path is correct, and treats it as a **build error inside a code block** — deliberately,
because no rewrite is safe there: stripping `python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py` to a
relative path does not fail loudly, it succeeds into a *different project's* `scripts/`.

So stanza A will fail that build, and that is the rule working — the author learns at package time
that a Claude-specific invocation does not port, rather than a user learning at run time. The form
it asks for instead is to resolve the directory once and pass an absolute path from then on:

```bash
export SKILL_DIR=/absolute/path/to/your-skill    # on Claude Code, the value the loader prepended
cd "$SKILL_DIR/scripts" && python3 -m your_package
```

Keep the quotes. Unquoted, an unset `$SKILL_DIR` word-splits to a bare `cd`, which succeeds into
`$HOME` and lets an `&&` chain continue from the wrong place.

## Why this order

The read path ranks **above** everything else, and that is deliberate. The path this file was loaded
with is the only form that proves the scripts belong to the same install as the instructions being
followed. A launcher on `PATH` proves *a* working install, not *that* one — with two installs
present and the launcher bound to the older, a launcher-first resolver runs the wrong version and
says nothing. Below it, prefer whatever the SHELL can establish for itself: a search proves the file exists
in the namespace that will run it, which is the one fact the read path cannot supply when the two
mounts diverge. A launcher is faster than a search but is not always present — see the measurement
above — so it is an optimisation on this tier, never the tier itself.

## What not to substitute in

`${CLAUDE_PLUGIN_ROOT}` looks like the right tool and is not. It is substituted into definition
text only, is absent from the Bash tool's contract, and its value is the file-tool-side path — the
wrong side of the split. `${CLAUDE_SKILL_DIR}` has the same three limits but at least names the
right directory. Neither survives a shell.

---

## Why the launcher has nine rules

Each came from a failure that was measured, not imagined. They live here rather than in
`plugin-bin-launcher.sh` because that file gets copied into your repo and this one does not — an
adopting plugin should carry the rules, not our investigation.

1. **`bin/` beside `.claude-plugin/plugin.json`.** PATH receives the plugin root. In a marketplace
   repo whose plugin sits in a subdirectory there are two candidate roots and only the inner one
   counts. A `bin/` elsewhere is usually an ordinary project CLI, correctly placed — this is about
   which directory PATH gets, not about tidying a repo.
2. **Resolve symlinks first.** `${BASH_SOURCE[0]}` is the invoking path, so a symlink on PATH makes
   the computed root the symlink's grandparent — wrong tree, exit 0, no complaint.
3. **A PATH entry is not evidence the directory exists.** The builder maps every enabled
   non-builtin plugin to `<root>/bin` with no existence check, so `echo $PATH` reads healthy on the
   actual failure and "command not found" never means PATH is misconfigured.
4. **Don't name it after a `clis` key.** On Cowork's org-remote lane a plugin root has a `bin/`
   **iff** `clis` is declared, and the runtime materialises `bin/<key>` itself as a wrapper shim on
   its own schedule.
5. **Commit the exec bit.** The plugin mount is read-only; it cannot be added after install.
6. **A bare name, never a path.** `"$ROOT/$SUBDIR/$1.py"` with an unchecked argument runs
   `../../anything`.
7. **An empty first argument is not "no arguments".** Grouped with `--help`, `cmd "$UNSET"` exits 0
   having done nothing while a typo exits 127 — the near-miss loud, the likelier failure silent.
8. **`${CLAUDE_PLUGIN_ROOT}` can be set and wrong.** A plugin's `Setup` / `SessionStart` /
   `CwdChanged` / `FileChanged` hook may export its own environment into the session, so an
   unrelated plugin's root lands in your shell and every later Bash call inherits it. Observed:
   `CLAUDE_PLUGIN_ROOT` naming one plugin beside a `CLAUDE_PLUGIN_DATA` naming another, neither
   being the plugin whose skill was running.

   **Check it yourself:** `ls ~/.claude/session-env/<session-id>/` — one file per hook, holding the
   exports your shell inherited. `CLAUDE_ENV_FILE` is *not* set in that shell; it is the path the
   hook was told to write to, so its absence there is the mechanism working, not evidence against
   it. This is why "is it empty?" is the wrong first question.
9. **A skill's scripts are not at the plugin root.** A plugin's own sit at `<root>/scripts`, a
   skill's at `<root>/skills/<skill>/scripts`. A launcher pinned to the wrong one fails as an empty
   `--list` and a bare 127.
