#!/usr/bin/env bash
# TEMPLATE — a plugin launcher for a CLI-INSTALLED plugin. Copy to <plugin root>/bin/<name>, set
# NAME, chmod 755, commit. If the plugin may be distributed through claude.ai organization
# settings, do not ship this file at all — see READ FIRST (2) below.
#
# Runs a script shipped with this plugin as a bare command, so no filesystem path has to travel
# from the file tools to the shell. Claude Code puts <plugin root>/bin on the Bash tool's PATH.
#
# READ FIRST — this is an OPTIMISATION, not a fallback. Measured: on a local session's host loop, the lane
# with the namespace split this exists to bridge, the shell's PATH carries no plugin bin/ at all.
# Gate every use on `command -v <name>` and keep a search branch behind it.
#
# READ FIRST (2) — LANE RESTRICTION. A top-level bin/ makes the plugin UNDISTRIBUTABLE through
# claude.ai organization settings: marketplace sync and direct upload both reject it with a message
# beginning "Plugin contains a top-level bin/ directory". `claude plugin validate --strict` does NOT
# warn (measured, 2.1.252), so a green pre-flight proves nothing here. GitHub and local CLI installs
# are unaffected. If this plugin might ever be published through an organization, DO NOT SHIP THIS
# FILE — the read-path-then-search stanza in assets/skill-script-invocation.md needs no launcher.
#
# NINE RULES, each from a measured failure. The evidence for each is in
# assets/skill-script-invocation.md (§ Why the launcher has nine rules) — kept there rather than
# here because this file gets copied into your repo and that does not.
#
#  1. bin/ SITS BESIDE .claude-plugin/plugin.json — not the repo root, not a source subtree.
#  2. RESOLVE SYMLINKS before computing the root; ${BASH_SOURCE[0]} is the invoking path.
#  3. VERIFY, DON'T TRUST — a PATH entry is advertised whether or not the directory exists.
#  4. DO NOT NAME IT AFTER A `clis` KEY in plugin.json; the runtime materialises bin/<key> itself.
#  5. COMMIT THE EXEC BIT (`git ls-files -s` shows 100755); the plugin mount is read-only.
#  6. A BARE NAME, NEVER A PATH — interpolating an argument allows `../../x`.
#  7. AN EMPTY FIRST ARGUMENT IS NOT "NO ARGUMENTS" — tell them apart by argument COUNT.
#  8. NEVER RELY ON ${CLAUDE_PLUGIN_ROOT}, and never debug it by checking whether it is empty.
#     In a shell it is usually empty but can be SET AND WRONG, naming an unrelated plugin.
#  9. SET SUBDIR, OR LEAVE IT "auto" — a skill's scripts are under skills/<skill>/scripts.

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
