#!/usr/bin/env bash
# TEMPLATE — a plugin launcher. Copy to <plugin root>/bin/<name>, set NAME, chmod 755, commit.
#
# WHAT IT SOLVES. A skill's instructions need to run `python3 <plugin>/scripts/foo.py`, but the
# model only knows the path it READ THE INSTRUCTION AT, which is a file-tool path. On some hosts
# (Cowork's host loop) the shell lives in a different filesystem namespace — not a different
# working directory, a different mount of the same content at a different absolute path — and no
# single string is correct for both. Claude Code puts <plugin root>/bin on the BASH TOOL'S PATH,
# constructed for that shell rather than inherited, so a bare `<name>` resolves in the shell's own
# namespace and no path crosses the boundary.
#
# WHERE THIS RANKS. Below the path the instruction was read at, not above it. A launcher on PATH
# proves *a* working install, not *that* install: with two installs present and the launcher bound
# to the older one — the ordinary shape of a maintainer's machine — a launcher-first resolver
# silently runs the wrong version. Use the read path when the shell can see it; use this when it
# cannot. See assets/skill-script-invocation.md for the stanza that encodes that order.
#
# NINE RULES, each from a measured failure. Ignore any and this breaks quietly.
#
#  1. bin/ SITS BESIDE .claude-plugin/plugin.json. Not the repo root, not a source subtree. PATH
#     receives the plugin root, so a bin/ one level out reaches nobody, and `find . -name bin`
#     calls it compliant. Check the sibling, not the name.
#  2. RESOLVE SYMLINKS FIRST. ${BASH_SOURCE[0]} is the invoking path, not the physical file, so a
#     symlink on PATH makes the root the symlink's grandparent — wrong tree, exit 0.
#  3. VERIFY, DON'T TRUST. A PATH entry is advertised whether or not the directory exists; the
#     builder has no existence check. So `echo $PATH` reads healthy on the actual failure, and
#     "command not found" never means PATH is misconfigured. Gate on `command -v`, not on PATH.
#  4. DO NOT NAME IT AFTER A `clis` KEY in plugin.json. On Cowork's org-remote lane a plugin root
#     has a bin/ IFF `clis` is declared, and the runtime materialises bin/<key> itself as a wrapper
#     shim on its own schedule. Declaring clis: {foo: ...} means the runtime owns bin/foo.
#  5. COMMIT THE EXEC BIT (`git ls-files -s` must show 100755). The plugin mount is read-only, so
#     it cannot be added after install.
#  6. A BARE NAME, NEVER A PATH. Interpolating an argument into "$ROOT/$SUBDIR/$1.py" lets
#     `../../x` run a file outside the plugin.
#  7. AN EMPTY FIRST ARGUMENT IS NOT "NO ARGUMENTS". Grouped with --help, `cmd "$UNSET"` exits 0
#     having done nothing, while a typo exits 127 — the near-miss loud, the likelier programmatic
#     failure silent. Tell them apart by argument COUNT.
#  9. SET SUBDIR, OR LEAVE IT "auto". A skill's scripts are at <root>/skills/<skill>/scripts,
#     NOT <root>/scripts. A launcher pinned to the wrong one fails as an empty --list and a bare
#     127 — measured, by following this template and the stanza verbatim.
#  8. NEVER RELY ON ${CLAUDE_PLUGIN_ROOT} FOR THIS, and do not debug it by checking for empty.
#     It is substituted into DEFINITION text (SKILL.md, commands/*.md) at load and arrives
#     literally in a reference file read at runtime. In a shell it is usually empty — but it can
#     also be SET AND WRONG: a plugin's SessionStart/Setup/CwdChanged/FileChanged hook may export
#     its own environment via CLAUDE_ENV_FILE, so an unrelated plugin's root lands in the session
#     env and every later Bash call inherits it. Measured: CLAUDE_PLUGIN_ROOT naming one plugin
#     beside a CLAUDE_PLUGIN_DATA naming another, neither being the plugin whose skill was running.
#     Its value is also the file-tool-side path, the wrong side of the split this exists to bridge.
#
# SCOPE — READ THIS BEFORE RELYING ON IT. The PATH mechanism is verified for Claude Code's own
# Bash tool: a bin/ at the plugin root resolves as a bare command there. It is NOT present in
# Cowork's host-loop workspace shell. Measured 2026-08-29 with this template installed in a
# harness-staged plugin: that shell's PATH was eight stock entries —
#   /usr/local/lib/node_modules_global/bin /usr/local/sbin /usr/local/bin /usr/sbin /usr/bin
#   /sbin /bin /snap/bin
# — with no plugin bin/ of any kind, so `command -v <name>` found nothing and the skill recovered
# only by searching the filesystem from the shell's side.
#
# That is the lane with the namespace split, i.e. the one this launcher was built to bridge. So it
# is an OPTIMISATION where PATH happens to carry it, never the fallback a skill depends on. Ship it
# if you like, gate every use on `command -v`, and keep a search branch behind it. See
# assets/skill-script-invocation.md, stanza B.
#
# Bound on that measurement: the plugin was staged locally by the harness. Whether a plugin synced
# through the org-remote path gets PATH treatment in that shell is not established either way.
#
# Also unverified: the client version that added bare-command bin/ lookup, and whether an AUTHORED
# launcher survives re-provisioning on the org-remote lane (nobody ships one, so there is no field
# evidence).

set -euo pipefail

NAME="CHANGEME"          # the command this installs as; must equal this file's basename
# Where the scripts live, relative to the plugin root. "auto" searches <root>/scripts and then
# every <root>/skills/*/scripts — which covers both layouts, since a PLUGIN's scripts sit at the
# root while a SKILL's sit under skills/<skill>/scripts. Set it explicitly to pin one directory.
SUBDIR="auto"
MIN_PY="3.8"

# Rule 2: resolve the symlink chain before computing the root.
src="${BASH_SOURCE[0]}"
while [ -L "$src" ]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  case "$src" in /*) ;; *) src="$dir/$src" ;; esac
done
ROOT="$(cd -P "$(dirname "$src")/.." && pwd)"

# Rule 9: a skill's scripts are NOT at the plugin root. A plugin's own live at <root>/scripts,
# a skill's at <root>/skills/<skill>/scripts, and a launcher that only knows the first finds
# nothing for the second — silently, as an empty --list and a bare 127.
script_dirs() {
  if [ "$SUBDIR" != "auto" ]; then printf '%s\n' "$ROOT/$SUBDIR"; return; fi
  [ -d "$ROOT/scripts" ] && printf '%s\n' "$ROOT/scripts"
  for d in "$ROOT"/skills/*/scripts; do [ -d "$d" ] && printf '%s\n' "$d"; done
  return 0
}

# Entry points only — ask each file rather than maintaining a denylist nothing checks.
list_scripts() {
  script_dirs | while IFS= read -r dir; do
    for f in "$dir"/*.py; do
      [ -e "$f" ] || continue
      grep -q '^if __name__ ==' "$f" || continue
      basename "$f" .py
    done
  done
  return 0
}

find_script() {
  script_dirs | while IFS= read -r dir; do
    if [ -f "$dir/$1.py" ]; then printf '%s\n' "$dir/$1.py"; break; fi
  done
  return 0
}

usage() {
  cat <<USAGE
$NAME — run a script shipped with this plugin.

Usage:
  $NAME <script> [args...]   run $SUBDIR/<script>.py (the .py is optional)
  $NAME --where              print the resolved plugin root and the script dirs
  $NAME --list               list the scripts available
  $NAME --help

Exit codes:
  0    the script succeeded
  1    the script refused — read its message
  78   python3 present but older than $MIN_PY
  127  python3 not found, no such script, or the argument was not a bare name

The script's exit code is passed through unchanged.
USAGE
}

# Rule 7: no arguments is a person; an empty first argument is a variable that did not expand.
if [ "$#" -eq 0 ]; then usage; exit 0; fi
if [ -z "$1" ]; then
  echo "$NAME: empty script name — a variable that did not expand?" >&2
  usage >&2
  exit 127
fi

case "$1" in
  -h|--help) usage; exit 0 ;;
  --where)   printf '%s\n' "$ROOT"; script_dirs | sed 's/^/  scripts: /'; exit 0 ;;
  --list)    list_scripts; exit 0 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "$NAME: python3 not found on \$PATH." >&2
  exit 127
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '$MIN_PY'.split('.')) else 1)"; then
  echo "$NAME: python3 $MIN_PY+ required (found $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])'))." >&2
  exit 78
fi

name="${1%.py}"; shift

# Rule 6: a name, not a path.
case "$name" in
  */*|.*)
    echo "$NAME: '$name' is not a script name — pass a bare name, not a path." >&2
    exit 127 ;;
esac

target="$(find_script "$name")"
if [ -z "$target" ]; then
  echo "$NAME: no such script '$name'. Looked in:" >&2
  script_dirs | sed 's/^/  /' >&2
  echo "Available:" >&2
  list_scripts | sed 's/^/  /' >&2
  exit 127
fi

exec python3 "$target" "$@"
