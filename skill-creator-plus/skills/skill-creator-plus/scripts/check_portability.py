#!/usr/bin/env python3
"""
Cross-runtime portability linter for skills.

skill-creator-plus can author skills for three runtimes — Claude Code, Claude.ai, and Claude
Cowork — whose capabilities differ. A construct that works in Claude Code can silently break
elsewhere: Claude.ai has no subagents and no `claude` CLI; Cowork has no browser/display and a
default-deny egress sandbox whose base image lacks third-party Python packages (and can't
pip-install them). `quick_validate.py` checks *structure*; this checks *runtime portability*.

It is deliberately STDLIB-ONLY (no PyYAML) — it has to run inside the very sandboxes it lints,
so it must not depend on anything those sandboxes might lack. Frontmatter is parsed with a small
purpose-built parser (enough for `name`/`description`/`when_to_use`/`compatibility`), and imports
are detected with `ast`.

Findings are advisory by default (exit 0) so the linter is safe to run on any skill; `--strict`
gates (exit 1) on any finding for the selected target, and a `description` over the hard 1,024-char
spec cap is always an error.

Usage:
  python -m scripts.check_portability <skill-dir> [--target claude-code|claude-ai|cowork|all]
                                      [--json] [--strict]
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

TARGETS = ("claude-code", "claude-ai", "cowork")

# agentskills.io / Claude listing caps (see references/official-guide-patterns.md).
DESC_HARD_CAP = 1024          # description field spec cap — over this is an ERROR
COMBINED_CAP = 1536           # description + when_to_use listing-entry truncation threshold
DESC_COLLAPSE_HINT = 800      # a single description this large materially feeds the ~8KB collapse

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_ADVISORY = "advisory"


def _finding(rule, severity, targets, message, location=None):
    return {
        "rule": rule,
        "severity": severity,
        "targets": sorted(targets),
        "message": message,
        "location": location,
    }


# ---- minimal, stdlib-only frontmatter parsing (no PyYAML) ---------------------------------

def parse_frontmatter(md_text):
    """Extract the top `---`-fenced block and parse the few scalar fields we need.

    Handles `key: value`, quoted values, and block scalars (`key: |` / `key: >`). This is NOT a
    general YAML parser — it only needs name/description/when_to_use/compatibility, which are
    always simple scalars in a SKILL.md. Returns a dict of str->str (missing keys absent).
    """
    m = re.match(r"^---\n(.*?)\n---", md_text, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    lines = body.split("\n")
    fields = {}
    i = 0
    key_re = re.compile(r"^([A-Za-z0-9_\-]+):\s?(.*)$")
    while i < len(lines):
        line = lines[i]
        km = key_re.match(line)
        if not km:
            i += 1
            continue
        key, rest = km.group(1), km.group(2)
        if rest.strip() in ("|", ">", "|-", ">-", "|+", ">+"):
            # block scalar: gather subsequent more-indented lines
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or lines[i] == ""):
                block.append(lines[i].lstrip())
                i += 1
            sep = "\n" if rest.strip().startswith("|") else " "
            fields[key] = sep.join(b for b in block).strip()
            continue
        val = rest.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        fields[key] = val
        i += 1
    return fields


# ---- checks -------------------------------------------------------------------------------

def check_description_length(fields):
    findings = []
    desc = fields.get("description", "") or ""
    wtu = fields.get("when_to_use", "") or ""
    dlen = len(desc)
    if dlen > DESC_HARD_CAP:
        findings.append(_finding(
            "desc-over-hard-cap", SEVERITY_ERROR, TARGETS,
            f"description is {dlen} chars — over the {DESC_HARD_CAP}-char agentskills.io spec cap; "
            f"downstream validators reject or truncate it.",
            "SKILL.md:description",
        ))
    combined = dlen + len(wtu)
    if wtu and combined > COMBINED_CAP:
        findings.append(_finding(
            "listing-entry-truncation", SEVERITY_WARNING, TARGETS,
            f"description + when_to_use is {combined} chars — over the {COMBINED_CAP}-char listing "
            f"entry cap; Claude truncates the entry, dropping trigger surface.",
            "SKILL.md:when_to_use",
        ))
    elif dlen > DESC_COLLAPSE_HINT:
        findings.append(_finding(
            "listing-collapse-risk", SEVERITY_ADVISORY, TARGETS,
            f"description is {dlen} chars — large descriptions eat the shared ~8KB skill-listing "
            f"budget; if it overflows, every skill collapses to name-only. Trim if the user runs many skills.",
            "SKILL.md:description",
        ))
    return findings


# Heuristic source scans. Conservative on purpose — WARN/ADVISORY, never gate silently, since
# these are text patterns that can have legitimate guarded uses.
_SUBAGENT_RE = re.compile(r"\bsub-?agent(s)?\b", re.IGNORECASE)
_SUBAGENT_GUARD_RE = re.compile(r"if available|if you have|otherwise inline|when available|no subagents", re.IGNORECASE)
_CLAUDE_CLI_RE = re.compile(r"\bclaude\s+-p\b|\bclaude\s+setup-token\b|subprocess.*\bclaude\b")
_BROWSER_RE = re.compile(r"\bwebbrowser\b|http\.server|HTTPServer|BaseHTTPRequestHandler|localhost:\d+|127\.0\.0\.1:\d+")


def _iter_text_files(skill_path):
    for rel in ("SKILL.md",):
        p = skill_path / rel
        if p.exists():
            yield p
    for sub in ("references", "agents", "commands"):
        d = skill_path / sub
        if d.is_dir():
            for p in sorted(d.rglob("*.md")):
                yield p


def _iter_scripts(skill_path):
    d = skill_path / "scripts"
    if d.is_dir():
        for p in sorted(d.rglob("*.py")):
            yield p


def check_runtime_constructs(skill_path):
    findings = []
    md_hits_subagent = []
    cli_hits = []
    browser_hits = []
    # scan instruction text (SKILL.md + references/agents) and scripts
    for p in list(_iter_text_files(skill_path)) + list(_iter_scripts(skill_path)):
        try:
            text = p.read_text()
        except OSError:
            continue
        rel = p.relative_to(skill_path)
        for n, line in enumerate(text.split("\n"), 1):
            if _SUBAGENT_RE.search(line) and not _SUBAGENT_GUARD_RE.search(line):
                md_hits_subagent.append(f"{rel}:{n}")
            if _CLAUDE_CLI_RE.search(line):
                cli_hits.append(f"{rel}:{n}")
            if _BROWSER_RE.search(line):
                browser_hits.append(f"{rel}:{n}")

    if md_hits_subagent:
        findings.append(_finding(
            "subagent-dependency", SEVERITY_WARNING, ["claude-ai"],
            f"references subagents at {len(md_hits_subagent)} site(s) without an 'if available' "
            f"guard — Claude.ai has no subagents. Ensure an inline (no-subagent) fallback exists. "
            f"First: {md_hits_subagent[0]}",
            md_hits_subagent[0],
        ))
    if cli_hits:
        findings.append(_finding(
            "claude-cli-dependency", SEVERITY_WARNING, ["claude-ai"],
            f"invokes the `claude` CLI (e.g. `claude -p`) at {len(cli_hits)} site(s) — the CLI is "
            f"absent on Claude.ai. Gate these steps or provide a fallback. First: {cli_hits[0]}",
            cli_hits[0],
        ))
    if browser_hits:
        findings.append(_finding(
            "browser-display-dependency", SEVERITY_WARNING, ["claude-ai", "cowork"],
            f"assumes a browser/local HTTP server at {len(browser_hits)} site(s) — Cowork and "
            f"Claude.ai have no display. Provide a static / no-server fallback. First: {browser_hits[0]}",
            browser_hits[0],
        ))
    return findings


def _stdlib_names():
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    # Fallback for <3.10: a conservative core set (only used to avoid false positives).
    return {
        "os", "sys", "re", "json", "argparse", "pathlib", "subprocess", "shutil", "tempfile",
        "typing", "collections", "itertools", "functools", "math", "random", "datetime", "time",
        "io", "csv", "ast", "zipfile", "hashlib", "urllib", "http", "unittest", "glob", "textwrap",
        "dataclasses", "enum", "logging", "importlib", "contextlib", "traceback", "string",
    }


def check_thirdparty_imports(skill_path):
    """Flag non-stdlib, non-local imports in bundled scripts — they break Cowork's isolated sandbox."""
    findings = []
    scripts = list(_iter_scripts(skill_path))
    if not scripts:
        return findings
    stdlib = _stdlib_names()
    local_mods = {p.stem for p in scripts} | {"scripts"}
    offenders = {}  # module -> first "file:line"
    for p in scripts:
        try:
            tree = ast.parse(p.read_text(), filename=str(p))
        except (OSError, SyntaxError):
            continue
        rel = p.relative_to(skill_path)
        for node in ast.walk(tree):
            roots = []
            if isinstance(node, ast.Import):
                roots = [(a.name.split(".")[0], node.lineno) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:  # relative import → local
                    continue
                if node.module:
                    roots = [(node.module.split(".")[0], node.lineno)]
            for root, lineno in roots:
                if root and root not in stdlib and root not in local_mods and root not in offenders:
                    offenders[root] = f"{rel}:{lineno}"
    for mod, loc in sorted(offenders.items()):
        findings.append(_finding(
            "thirdparty-import", SEVERITY_WARNING, ["cowork"],
            f"bundled script imports third-party module `{mod}` — Cowork's base image lacks it and "
            f"default-deny egress blocks `pip install`, so this step fails or no-ops there (also a "
            f"risk on any network-isolated sandbox). Vendor it or degrade gracefully. At {loc}.",
            loc,
        ))
    return findings


def lint_portability(skill_path):
    """Return (all_findings, structural_error_or_None)."""
    skill_path = Path(skill_path)
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return [], "SKILL.md not found"
    fields = parse_frontmatter(skill_md.read_text())
    findings = []
    findings += check_description_length(fields)
    findings += check_runtime_constructs(skill_path)
    findings += check_thirdparty_imports(skill_path)
    return findings, None


def _filter_by_target(findings, target):
    if target == "all":
        return findings
    return [f for f in findings if target in f["targets"]]


def main():
    parser = argparse.ArgumentParser(
        description="Lint a skill for cross-runtime portability (Claude Code / Claude.ai / Cowork).",
        epilog=(
            "Examples:\n"
            "  python -m scripts.check_portability ./my-skill\n"
            "  python -m scripts.check_portability --target claude-ai ./my-skill\n"
            "  python -m scripts.check_portability --json --strict ./my-skill\n"
            "\n"
            "Targets: claude-code | claude-ai | cowork | all (default: all)\n"
            "\n"
            "Exit codes:\n"
            "  0  no blocking findings (advisory/warnings printed unless --strict)\n"
            "  1  a finding gates: an over-cap description (always), or any finding under --strict\n"
            "  2  usage error\n"
            "  3  skill directory / SKILL.md not found"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("skill_path", help="Path to the skill directory to lint")
    parser.add_argument("--target", choices=[*TARGETS, "all"], default="all",
                        help="Only report findings relevant to this runtime (default: all)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any finding is reported for the selected target")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    if not skill_path.exists():
        msg = f"Skill directory not found: {skill_path}"
        if args.json:
            print(json.dumps({"ok": False, "error": msg, "skill_path": str(skill_path)}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        sys.exit(3)

    findings, structural_error = lint_portability(skill_path)
    if structural_error:
        if args.json:
            print(json.dumps({"ok": False, "error": structural_error, "skill_path": str(skill_path)}))
        else:
            print(f"Error: {structural_error}", file=sys.stderr)
        sys.exit(3)

    shown = _filter_by_target(findings, args.target)
    has_hard_error = any(f["severity"] == SEVERITY_ERROR for f in shown)
    gate = has_hard_error or (args.strict and len(shown) > 0)

    if args.json:
        print(json.dumps({
            "ok": not gate,
            "target": args.target,
            "findings": shown,
            "skill_path": str(skill_path),
        }, indent=2))
    else:
        if not shown:
            print(f"✓ portability: no findings for target '{args.target}'.")
        else:
            print(f"Portability findings for target '{args.target}':\n")
            icon = {SEVERITY_ERROR: "✗", SEVERITY_WARNING: "⚠", SEVERITY_ADVISORY: "·"}
            for f in shown:
                tg = ", ".join(f["targets"])
                loc = f" ({f['location']})" if f.get("location") else ""
                print(f"  {icon.get(f['severity'], '-')} [{f['rule']}] ({tg}){loc}\n    {f['message']}")
            print(f"\n{len(shown)} finding(s). "
                  + ("gating (--strict or over-cap description)." if gate else "advisory — exit 0. Use --strict to gate."))
    sys.exit(1 if gate else 0)


if __name__ == "__main__":
    main()
