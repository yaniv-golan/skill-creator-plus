---
name: gizmo-probe
description: Probe gizmo definitions. Use when the user asks to "run the gizmo probe", "probe a gizmo", or "check my gizmo".
---

# Gizmo Probe

When the user asks to run the gizmo probe, run this skill's probe script with `--selftest` and
report the exact line it printed. The script needs no input file; do not ask for one.

**Running this skill's scripts.** Prefer the absolute path this file was loaded with:

    python3 ${CLAUDE_SKILL_DIR}/scripts/probe.py [args]

If the shell reports that path missing, you are on a host where the shell and the file tools are
different mounts of the same content (Cowork's host loop). **Do not guess, rewrite, or transform
that path** — the mapping is not something you can infer, and a guessed path that happens to work
is luck. Locate the file from the SHELL's side and run exactly what it finds:

    find / -path "*gizmo-probe/scripts/probe.py" -print -quit 2>/dev/null

Do not type `$CLAUDE_SKILL_DIR` or `$CLAUDE_PLUGIN_ROOT` into a shell command. Neither is
exported: the first expands to nothing, and the second may be set to a *different* plugin's
directory, so checking whether it is empty will not tell you it is wrong.
