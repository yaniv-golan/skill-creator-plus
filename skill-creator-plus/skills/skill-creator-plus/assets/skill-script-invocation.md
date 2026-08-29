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
