#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ $# -eq 1 ]; then
  echo "$1" > "$REPO_ROOT/VERSION"
fi

VERSION=$(cat "$REPO_ROOT/VERSION" | tr -d '[:space:]')
echo "Propagating version: $VERSION"

# 1. plugin.json
PLUGIN_JSON="$REPO_ROOT/skill-creator-plus/.claude-plugin/plugin.json"
if [ -f "$PLUGIN_JSON" ]; then
  python3 -c "
import json, sys
path = sys.argv[1]
ver = sys.argv[2]
with open(path) as f: data = json.load(f)
data['version'] = ver
with open(path, 'w') as f: json.dump(data, f, indent=2); f.write('\n')
print(f'  Updated {path}')
" "$PLUGIN_JSON" "$VERSION"
fi

# 2. SKILL.md frontmatter metadata.version (if present)
SKILL_MD="$REPO_ROOT/skill-creator-plus/skills/skill-creator-plus/SKILL.md"
if [ -f "$SKILL_MD" ] && grep -q 'metadata:' "$SKILL_MD"; then
  python3 -c "
import re, sys
path, ver = sys.argv[1], sys.argv[2]
text = open(path).read()
text = re.sub(r'(metadata:\s*\n\s*.*\n\s*version:\s*\")([^\"]+)(\")', lambda m: m.group(1)+ver+m.group(3), text)
open(path,'w').write(text)
print(f'  Updated {path}')
" "$SKILL_MD" "$VERSION"
fi

echo "Done. Version is now $VERSION"
