---
name: widget-check
description: Validate widget definition files. Use when the user asks to "run the widget check", "check my widget", or "validate a widget".
---

# Widget Check

When the user asks to run the widget check, run this skill's validation script with `--selftest` and
report the exact line it printed. The script needs no input file; do not ask for one.

**Running this skill's scripts.** Use the absolute path this file was loaded with:

    python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py [args]

Do not type `$CLAUDE_SKILL_DIR` into a shell command — it is a load-time text substitution, not an
environment variable, and expands to nothing in a shell. Read the resolved path out of this line
and pass it along verbatim, including to any sub-agent.
