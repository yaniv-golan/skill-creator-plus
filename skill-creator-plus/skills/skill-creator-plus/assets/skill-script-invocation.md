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

## B. With a `bin/` launcher (see `assets/plugin-bin-launcher.sh`)

```markdown
**Running this skill's scripts.** Prefer the absolute path this file was loaded with:

    python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py [args]

If the shell reports that path missing, it is in a different filesystem namespace from the file
tools (Cowork's host loop does this). Fall back to the bundled launcher, which resolves in the
shell's own namespace:

    command -v <cmd> >/dev/null && <cmd> <script> [args]

Do not type `$CLAUDE_SKILL_DIR` or `$CLAUDE_PLUGIN_ROOT` into a shell command. Neither is
exported: the first expands to nothing, and the second may be set to a *different* plugin's
directory, so checking whether it is empty will not tell you it is wrong.
```

---

## Why this order

The read path ranks **above** the launcher, and that is deliberate. The path this file was loaded
with is the only form that proves the scripts belong to the same install as the instructions being
followed. A launcher on `PATH` proves *a* working install, not *that* one — with two installs
present and the launcher bound to the older, a launcher-first resolver runs the wrong version and
says nothing. The launcher earns its place only where the read path is invisible to the shell,
which is exactly the namespace split it exists to bridge.

## What not to substitute in

`${CLAUDE_PLUGIN_ROOT}` looks like the right tool and is not. It is substituted into definition
text only, is absent from the Bash tool's contract, and its value is the file-tool-side path — the
wrong side of the split. `${CLAUDE_SKILL_DIR}` has the same three limits but at least names the
right directory. Neither survives a shell.
