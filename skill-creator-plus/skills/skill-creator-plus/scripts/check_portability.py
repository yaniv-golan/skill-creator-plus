#!/usr/bin/env python3
"""
Cross-runtime portability linter for skills.

skill-creator-plus can author skills for three runtimes — Claude Code, the Claude app's chat
runtime (target `claude-ai`), and the Claude app's cloud and local sessions (target `cowork`, named
for Claude Cowork) — whose capabilities differ. A construct that works in Claude Code can silently
break elsewhere: the Claude app's chat runtime has no sub-agent tool and no `claude` CLI (but a
Claude app conversation can run in a cloud session, which has a sub-agent tool — so a skill should
check its tool list, not the product name); cloud and local sessions have no browser/display and ship
a large but finite preinstalled Python stack (an import outside it costs an install on every run,
and egress is org-configurable so a locked-down org can deny that install), and file-delivery tools
differ per surface (cloud and local sessions serve different ones, and an agent sees only its own —
naming only one in skill text strands the surface served by the other; the correct pattern phrases delivery by outcome and names no tool — naming
both, capability-conditionally, is also acceptable — and never gates producing the artifact itself
on either being available). `quick_validate.py` checks *structure*; this checks *runtime
portability*.

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
# portability-allow: file-delivery-tool
# ^ This module necessarily contains the very tool names the `delivery-tool-single-lane` /
# `delivery-conditional-deliverable` rules look for, and `_iter_scripts()` scans
# `scripts/**/*.py` including this file. See references/environments.md for the constraint
# these rules enforce.

import argparse
import ast
import json
import math
import re
import sys
from pathlib import Path

# `claude-ai` means the Claude app's CHAT runtime, not every Claude app conversation: one can run
# as (or start partway through) a cloud session, which has a sub-agent tool and a shell, and that case
# is what `cowork` covers. The ids name runtimes by product for CLI stability; findings should say
# what the runtime lacks, so an author checks the tool list rather than the product.
TARGETS = ("claude-code", "claude-ai", "cowork")

# agentskills.io / Claude listing caps (see references/official-guide-patterns.md).
DESC_HARD_CAP = 1024          # description field spec cap — over this is an ERROR
COMBINED_CAP = 1536           # description + when_to_use listing-entry truncation threshold
DESC_BUDGET_HINT = 800        # a single description this large is a top contributor to the shared listing budget

# Import roots (not PyPI names) confirmed preinstalled in Cowork's VM image by a live probe on
# 2026-08-05 — Python 3.10.12, image shipping with Claude Desktop 1.25927.0. This is the LOCAL lane's
# image; a later read of the image shipped with Desktop 2.9939.2 is consistent with it (Python 3.10,
# numpy 2.2.6). The cloud sandbox ships a different image (seen with Python 3.11 and extra packages
# such as scipy); do not add cloud-only modules here, or the rule goes silent for a local run that
# lacks them. Importing one of these
# in a bundled script is not a Cowork portability risk, so `thirdparty-import` stays silent for it.
# This is observed state on ONE image in ONE org, not a published contract: it will drift, and a
# much newer image should be re-probed rather than trusted against this list. A module dropped from
# a future image becomes a silent false negative here — the harness's runtime ModuleNotFoundError
# guard is the backstop. Probed 2026-08-05; the maintainers' runtime-claims verification pass § F8
# holds the evidence (not in-repo: docs/internal/ is gitignored).
COWORK_PREINSTALLED = frozenset({
    "numpy",       # numpy 2.2.6
    "pandas",      # pandas 2.3.3
    "requests",    # requests 2.34.2
    "yaml",        # PyYAML 6.0.3
    "bs4",         # beautifulsoup4 4.15.0
    "openpyxl",    # openpyxl 3.1.5
    "PIL",         # Pillow 12.2.0
    "matplotlib",  # matplotlib 3.10.9
    "docx",        # python-docx 1.2.0
    "pptx",        # python-pptx 1.0.2
})

# Post-compaction re-attachment truncates each invoked skill's content to this many CHARACTERS.
# DERIVED ARITHMETIC, not a literal: the runtime slices to (5,000-token cap x 4) minus the
# 100-character truncation marker => 19,900. No `19900` appears anywhere in the bundle; don't go
# looking for one. The marker is `\n\n[... skill content truncated for compaction; use Read on
# the skill path if you need the full text]` — 98 visible characters PLUS two leading newlines.
# Measuring only the bracketed text yields 98 and a wrong cap of 19,902; a grep anchored on `[`
# cannot see the newlines at all. Re-verified byte-exact in 2.1.247. The per-skill cap (5,000) and the combined cross-skill cap (25,000) are
# hardcoded with no context-window scaling — verified first-party in 2.1.222 (Nvy/$vy), 2.1.246
# (V3o/K3o) and 2.1.247 (YJo/ZJo): three builds, three minified namings, identical values.
# The size function is RESOLVED, not inferred: `function $c(e,t=4){if(typeof e!=="string")return 0;
# return Math.round(e.length/t)}` — read out of 2.1.251 by following the truncator chunk's
# `import{$c,...}from"/$bunfs/root/chunk-raebvt7y.js"` to that chunk's bare `export{$c,...}` block.
# A bare-name grep can miss it in builds that alias-mangle the export (2.1.246); following the
# consuming chunk's import through the exporting chunk's export block works in both layouts.
# So the budget is LITERALLY a character gate — `wc -m` has zero conversion error. A tokenizer
# reading is not merely the wrong unit; it measures a quantity the runtime never computes, and on
# technical markdown (~3 chars/token) reads ~35% HIGHER than chars/4, overstating the overage.
# Truncation is destructive in the common case: the shortened text is written back to the registry,
# so a second compaction cannot recover the tail. That write-back is CONDITIONAL — it is skipped
# when the skill's content is already present in the conversation body, and a skill already carried
# as an attachment is not re-attached, truncated or zeroed at all. The size finding holds on every
# branch, which is why this rule is advisory on length alone.
COMPACTION_TOKEN_CAP = 5000        # runtime `N1n`, the per-skill cap `$c(text)` is compared to
COMPACTION_MARKER_CHARS = 100      # `\n\n` + 98 visible chars of the truncation marker
COMPACTION_CAP_CHARS = COMPACTION_TOKEN_CAP * 4 - COMPACTION_MARKER_CHARS   # 19,900

# What TRIGGERS truncation is a different quantity from what SURVIVES it, and they are 102 chars
# apart. The runtime returns the content untouched when `$c(text) <= 5000`, i.e. when
# `Math.round(len/4) <= 5000`. JS `Math.round` is half-up, so:
#     len 20,001 -> 5000.25 -> 5000  -> untouched
#     len 20,002 -> 5000.50 -> 5001  -> TRUNCATED
# Gating on COMPACTION_CAP_CHARS (19,900) therefore flags 19,901..20,001 as at-risk when the
# runtime never touches them. Gate on the trigger; report against the survivor.
# floor(n/4 + 0.5) > 5000  <=>  n >= 20002. Spelled out rather than written as a literal so the
# two constants cannot drift apart if the runtime's cap ever moves.
COMPACTION_TRIGGER_CHARS = 4 * COMPACTION_TOKEN_CAP + 2                     # 20,002

# The COMBINED cap across every skill re-attached in one session (runtime `$1n`, binary-verified
# 5,000/25,000 across 2.1.222/246/247/251). Its failure mode is categorically worse than the
# per-skill one and is the reason this rule exists at all:
#
#     if (o + F > $1n) { if (!x) w5t(_, ""); continue; }
#
# Truncation announces itself — it appends a marker, so an agent can notice the tail is gone and
# re-read from disk. Blowing the COMBINED cap does not: the skill is written back as the EMPTY
# STRING and omitted from the attachment entirely. No marker, no entry, nothing to compare
# against. A running session cannot detect it, which makes authoring time the only place it IS
# detectable — hence a lint rule for something that never fires on one skill in isolation.
#
# Packing is greedy in most-recently-invoked-first order, so `sum > cap` is exact for "at least
# one skill is dropped" — and the one dropped is the least-recently-invoked, NOT the largest.
COMBINED_TOKEN_CAP = 25000

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
            f"description + when_to_use is {combined} chars — over the {COMBINED_CAP}-char "
            f"listing-entry cap (the skillListingMaxDescChars default); Claude truncates the "
            f"entry, dropping trigger surface.",
            "SKILL.md:when_to_use",
        ))
    elif dlen > DESC_BUDGET_HINT:
        findings.append(_finding(
            "listing-desc-drop-risk", SEVERITY_ADVISORY, TARGETS,
            f"description is {dlen} chars — Claude's skill listing shares one budget (~1% of the "
            f"context window) across every installed skill, and on overflow it drops whole "
            f"descriptions starting with the least-recently-used skills. A description this large "
            f"is a top contributor to that overflow, and it is this skill's own description that "
            f"goes name-only once the user stops invoking it regularly. Trim it.",
            "SKILL.md:description",
        ))
    return findings


# Heuristic source scans. Conservative on purpose — WARN/ADVISORY, never gate silently, since
# these are text patterns that can have legitimate guarded uses.
_SUBAGENT_RE = re.compile(r"\bsub-?agent(s)?\b", re.IGNORECASE)
_SUBAGENT_GUARD_RE = re.compile(r"if available|if you have|otherwise inline|when available|no subagents", re.IGNORECASE)
_CLAUDE_CLI_RE = re.compile(r"\bclaude\s+-p\b|\bclaude\s+setup-token\b|subprocess.*\bclaude\b")
_BROWSER_RE = re.compile(r"\bwebbrowser\b|http\.server|HTTPServer|BaseHTTPRequestHandler|localhost:\d+|127\.0\.0\.1:\d+")

# File-delivery tools are per-surface: no single name is served everywhere — cloud and local sessions
# serve different ones (a local session serves `present_files`, a cloud session serves
# `SendUserFile`, also native to Claude Code), and an agent only sees the one for its surface.
# Naming only one in skill text strands the lane served by the other; the correct pattern phrases
# delivery by outcome and names no tool (naming BOTH, capability-conditionally, is also acceptable
# and stays clean — see references/environments.md). Both rules below therefore carry the full
# `TARGETS` — a single-lane skill can misbehave on any of the three runtimes depending on which
# kind of session (or product) it lands on.
# Fixed iteration order → deterministic finding order regardless of scan order.
# NOT EXHAUSTIVE, deliberately: Claude Code tracks four delivery channels (`artifact`,
# `cowork_present_files`, `send_user_file`, `brief`); these two are the ones whose *names* appearing
# in skill text strand a lane. The rules are about single-lane naming, not about enumerating every
# way a file can reach a user.
_DELIVERY_TOOL_RES = (
    ("present_files", re.compile(r"\b(?:mcp__[A-Za-z0-9_]+__)?present_files\b")),
    ("SendUserFile", re.compile(r"\bSendUserFile\b")),
)
# The distinguisher for `delivery-conditional-deliverable` is *skipping/omitting the artifact's
# production*, not conditionality as such — "if a tool is available, use it; otherwise state the
# path" is the correct, target-state pattern and must NOT match this, even when it happens to use
# "only if" or "if you don't have" to phrase the tool-availability check. What separates a real bug
# (gating packaging/writing itself) from a correct capability-conditional presentation is:
#   (a) a production verb — package/zip/write/save/generate/create/build — in the same clause as
#       the skip/omit phrase (a skip/omit phrase with no production verb nearby is talking about
#       *presenting*, not *producing*, the file); and
#   (b) no stated fallback (e.g. "otherwise state the path") — a fallback means the deliverable is
#       never actually skipped, only the presentation tool call is.
# Matched per-clause (sentence-scoped), not per physical line, so wrapping the same instruction
# across lines cannot change the verdict — see `_iter_clauses()`.
_DELIVERY_SKIP_OMIT_RE = re.compile(
    r"\bskip (?:this|it|that)\b|\bonly if\b|\bif you don't have\b|\bomit(?:s|ted|ting)?\b",
    re.IGNORECASE,
)
_DELIVERY_PRODUCTION_VERB_RE = re.compile(
    r"\b(?:packag(?:e|es|ed|ing)|zip(?:s|ped|ping)?|writ(?:e|es|ing|ten|e)|"
    r"sav(?:e|es|ed|ing)|generat(?:e|es|ed|ing)|creat(?:e|es|ed|ing)|"
    r"build(?:s|ing)?|built)\b",
    re.IGNORECASE,
)
_DELIVERY_FALLBACK_RE = re.compile(
    r"\botherwise state\b|\bstate the path\b|\btell(?:s|ing)? the user where\b",
    re.IGNORECASE,
)
# Explicit, greppable, file-scoped opt-out — for the two kinds of file that must name these tools:
# this linter's own source, and the doc that teaches the constraint. A phrase-list guard cannot work
# here (it would have to match the linter's own implementation); see D5.
#
# Requires comment context (a leading `#` comment line, or an HTML `<!-- -->` comment) so that mere
# *prose describing* the marker (e.g. a doc explaining "suppress this with a `portability-allow:
# file-delivery-tool` comment") cannot silently disable the rule it's describing — only an actual
# marker directive can.
# A RELATIVE `outputs/...` path naming a workspace. Deliberately narrow: boundary-anchored so
# `with_skill/outputs/` and `<run-dir>/outputs/` can't match, optional `./` because that form
# normalises and doubles identically, and it must resolve to a `-workspace` directory. A wider rule
# would have to guess what base a bare `outputs/` is relative to, which is how the earlier
# `file-delivery-tool-hardcoded` rule ended up firing on correct text.
_OUTPUTS_WORKSPACE_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s`('\"\[*=:>]))(?:\./)?outputs/[^\s`'\"|*]*?[-_]?workspace\b"
)

# HTML-comment form ONLY. check_outputs_prefix scans markdown, where a leading `#` is a heading,
# not a comment — accepting it would let a fenced example or a section title silently blind the
# whole file, which is the most natural way someone documents the escape hatch.
_OUTPUTS_ALLOW_RE = re.compile(r"<!--\s*portability-allow:\s*outputs-prefix\s*-->")

_DELIVERY_ALLOW_RE = re.compile(
    r"(?m)^[ \t]*#[ \t]*portability-allow:\s*file-delivery-tool\b"
    r"|<!--\s*portability-allow:\s*file-delivery-tool\s*-->"
)


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


def _iter_clauses(text):
    """Split text into loose clause/sentence windows, each tagged with its 1-based start line.

    A boundary is sentence-ending punctuation followed by whitespace, or a blank line
    (paragraph break). Wrapped physical lines with no sentence-ending punctuation at the wrap
    point stay joined into a single clause — this is what makes `delivery-conditional-deliverable`
    immune to line-wrapping: the same instruction reads as the same clause regardless of where an
    author happened to break the line.
    """
    boundary_re = re.compile(r"(?<=[.!?])\s+|\n[ \t]*\n")
    pos = 0
    for m in boundary_re.finditer(text):
        clause = text[pos:m.start()]
        if clause.strip():
            yield clause, text.count("\n", 0, pos) + 1
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        yield tail, text.count("\n", 0, pos) + 1


def check_compaction_budget(skill_md_text):
    """Flag a SKILL.md whose tail will be dropped when a session auto-compacts.

    Exact, not heuristic: the runtime's size function is `Math.round(chars/4)` and the cap it is
    compared against is a hardcoded 5,000, so the whole budget reduces to a character comparison —
    no tokenizer, no estimate, no divisor to tune.

    Two constants, deliberately: truncation FIRES at COMPACTION_TRIGGER_CHARS (20,002) and what
    SURVIVES it is COMPACTION_CAP_CHARS (19,900), the rest replaced by a 100-character marker.
    """
    findings = []
    n = len(skill_md_text)
    if n < COMPACTION_TRIGGER_CHARS:
        return findings
    cut_line = skill_md_text[:COMPACTION_CAP_CHARS].count("\n") + 1
    findings.append(_finding(
        "compaction-truncation-risk", SEVERITY_ADVISORY, ["claude-code", "cowork"],
        f"SKILL.md is {n:,} chars — {n / COMPACTION_CAP_CHARS:.2f}x the {COMPACTION_CAP_CHARS:,}-char "
        f"limit that survives auto-compaction. Everything after roughly line {cut_line} is dropped "
        f"once a session compacts. In the common case the truncation is written back, so a second "
        f"compaction cannot recover the tail — only re-reading the file from disk can (the "
        f"write-back is skipped when the content is already in the conversation body). This is a "
        f"CHARACTER budget: measure "
        f"with `wc -m` (not `wc -c`, which counts bytes, and not a tokenizer, which measures a unit "
        f"the budget never consults and reads ~35% high here). To fix, move whole phases into "
        f"references/ rather than trimming prose.",
        "SKILL.md",
    ))
    return findings


def attached_token_cost(n_chars):
    """What a SKILL.md of `n_chars` contributes to the combined budget, in the runtime's units.

    The runtime sums `$c(M)` where `M` is the ALREADY-TRUNCATED content, so an over-cap skill
    costs exactly the per-skill cap and no more: truncation leaves CAP chars plus the 100-char
    marker, i.e. `TOKEN_CAP * 4` chars exactly, i.e. `TOKEN_CAP` tokens.
    """
    if n_chars >= COMPACTION_TRIGGER_CHARS:
        return COMPACTION_TOKEN_CAP
    # JS `Math.round` is half-up; Python's round() is banker's rounding and would be wrong here.
    return math.floor(n_chars / 4 + 0.5)


def find_plugin_root(skill_path):
    """Return the plugin root containing `skill_path`, or None if the skill is standalone.

    Walks up for `.claude-plugin/plugin.json` rather than guessing from directory names. In a
    marketplace repo whose plugin lives in a subdirectory there are two candidate roots and only
    the inner one is the plugin — the nearest ancestor with a manifest, which is what this returns.
    """
    skill_path = Path(skill_path).resolve()
    for parent in [skill_path, *skill_path.parents]:
        if (parent / ".claude-plugin" / "plugin.json").is_file():
            return parent
    return None


def find_plugin_skill_siblings(skill_path):
    """Return every `skills/*/SKILL.md` of the plugin containing `skill_path`, or [] if standalone.

    A skill that is not inside a plugin has no combined budget to blow on its own, so it gets [].
    """
    root = find_plugin_root(skill_path)
    return sorted(root.glob("skills/*/SKILL.md")) if root else []


def check_combined_compaction_budget(skill_path):
    """Flag a PLUGIN whose skills cannot all be re-attached after one session compacts.

    Scoped deliberately as a lower bound: the runtime's budget is over the skills INVOKED in a
    session, across every enabled plugin, not over one plugin's skills. So this fires only on the
    narrower, fully author-controlled case — every skill in THIS plugin invoked, and nothing else.
    A session that also invokes skills from other plugins blows the cap sooner, never later.
    """
    findings = []
    sheets = find_plugin_skill_siblings(skill_path)
    if len(sheets) < 2:
        return findings
    costs = []
    for md in sheets:
        try:
            costs.append((md, attached_token_cost(len(md.read_text(encoding="utf-8")))))
        except OSError:
            continue
    total = sum(c for _, c in costs)
    if total <= COMBINED_TOKEN_CAP:
        return findings
    biggest = ", ".join(
        f"{md.parent.name} ({c:,})"
        for md, c in sorted(costs, key=lambda mc: -mc[1])[:3]
    )
    findings.append(_finding(
        "compaction-zeroing-risk", SEVERITY_ADVISORY, ["claude-code", "cowork"],
        f"This plugin's {len(costs)} skills cost {total:,} tokens once re-attached — over the "
        f"{COMBINED_TOKEN_CAP:,}-token COMBINED cap. If a session invokes all of them and then "
        f"compacts, at least one is dropped WHOLE: written back as the empty string and omitted "
        f"from the attachment. Unlike truncation there is no marker and no entry, so a running "
        f"session cannot detect it or recover — authoring time is the only place this is visible. "
        f"Eviction is least-recently-invoked-first, so the skill that vanishes is rarely the "
        f"largest. Costs are POST-truncation, which caps any single skill at "
        f"{COMPACTION_TOKEN_CAP:,}: largest are {biggest}. To fix, merge or drop skills, or move "
        f"detail into references/ (read on demand, never counted). Lower bound — skills from "
        f"other enabled plugins share this same budget.",
        ".claude-plugin/plugin.json",
    ))
    return findings


def check_plugin_bin_directory(skill_path):
    """Flag a PLUGIN that ships a top-level `bin/` — undistributable through org settings.

    Not a degradation: claude.ai rejects the plugin outright, by marketplace sync and by direct
    upload alike, with a message beginning `Plugin contains a top-level bin/ directory`. The stated
    reason is that those entries are added to PATH on the CLI but never appear on the admin
    approval surface. `claude plugin validate` does NOT warn (measured on 2.1.252 against a plugin
    carrying a `bin/` entry: `validate .` and `validate . --strict` reported only an unrelated
    `author` warning), so the pre-flight gate authors are told to run is green on a plugin that
    cannot be published. That is what makes this worth a lint rule rather than a doc line.

    Scoped to `claude-ai` because the restriction is lane-specific and NOT a deprecation: a
    top-level `bin/` is entirely correct for a plugin installed from GitHub or the local CLI, where
    it is on the Bash tool's PATH. So this is a WARNING, gating only under `--strict`.

    Fires on the plugin root only — the directory holding `.claude-plugin/plugin.json`. A `bin/`
    anywhere else (a repo root above the plugin, a skill's own subtree) is not what intake reads.
    An existent-but-empty `bin/` does not fire: git cannot commit one, so it never ships.
    """
    findings = []
    root = find_plugin_root(skill_path)
    if root is None:
        return findings
    bin_dir = root / "bin"
    if not bin_dir.is_dir():
        return findings
    try:
        entries = sorted(p.name for p in bin_dir.iterdir())
    except OSError:
        return findings
    if not entries:
        return findings
    shown = ", ".join(f"bin/{n}" for n in entries[:3])
    more = f" (+{len(entries) - 3} more)" if len(entries) > 3 else ""
    findings.append(_finding(
        "plugin-bin-directory", SEVERITY_WARNING, ["claude-ai"],
        f"This plugin ships a top-level bin/ directory ({shown}{more}), which makes it "
        f"UNDISTRIBUTABLE through claude.ai organization settings — org marketplace sync and "
        f"direct upload both reject it with a message beginning `Plugin contains a top-level bin/ "
        f"directory`, because those entries reach the CLI's PATH without appearing on the admin "
        f"approval surface. `claude plugin validate --strict` does not warn about this, so a green "
        f"pre-flight does not clear it. The restriction is lane-specific, not a deprecation: "
        f"GitHub and local-CLI installs are unaffected, so ignore this if the plugin is CLI-only. "
        f"Otherwise move the executables to scripts/. Reference them as "
        f"${{CLAUDE_PLUGIN_ROOT}}/scripts/<name> from a hook or mcpServers config, where that "
        f"token IS substituted; from a skill that shells out it expands to the empty string, so "
        f"use the read-path-then-search stanza in assets/skill-script-invocation.md instead.",
        "bin/",
    ))
    return findings


def check_runtime_constructs(skill_path):
    findings = []
    md_hits_subagent = []
    cli_hits = []
    browser_hits = []
    conditional_findings = []
    # `delivery-tool-single-lane` is decided SKILL-WIDE, not per file: the defect it flags —
    # "this skill strands a lane" — is a property of the skill, not of an individual file. A
    # skill that documents `present_files` in one reference doc and `SendUserFile` in another is
    # a legitimate structure and must not be flagged; per-file scoping would false-positive on
    # exactly that split (two findings, one per file, each seeing only one tool) even though the
    # skill as a whole names both. The accepted trade-off is the mirror-image false negative: a
    # skill could name the second tool somewhere unrelated to its delivery instructions and still
    # pass. That's the right side to err on here — a missed finding is cheap, but firing on a
    # skill that correctly documents both lanes (just split across files) is exactly the kind of
    # "fires on the correct answer" failure this rule replaced `file-delivery-tool-hardcoded` to
    # fix.
    skill_tool_first_loc = {}  # tool name -> first "file:line" ANYWHERE IN THE SKILL
    # scan instruction text (SKILL.md + references/agents) and scripts
    for p in list(_iter_text_files(skill_path)) + list(_iter_scripts(skill_path)):
        try:
            text = p.read_text()
        except OSError:
            continue
        rel = p.relative_to(skill_path)
        delivery_exempt = bool(_DELIVERY_ALLOW_RE.search(text))
        for n, line in enumerate(text.split("\n"), 1):
            if _SUBAGENT_RE.search(line) and not _SUBAGENT_GUARD_RE.search(line):
                md_hits_subagent.append(f"{rel}:{n}")
            if _CLAUDE_CLI_RE.search(line):
                cli_hits.append(f"{rel}:{n}")
            if _BROWSER_RE.search(line):
                browser_hits.append(f"{rel}:{n}")
            if delivery_exempt:
                continue
            line_tools = [tool for tool, rx in _DELIVERY_TOOL_RES if rx.search(line)]
            for tool in line_tools:
                if tool not in skill_tool_first_loc:
                    skill_tool_first_loc[tool] = f"{rel}:{n}"

        # `delivery-conditional-deliverable`, unlike single-lane, genuinely is a property of the
        # individual instruction — stays per-file/per-clause (not skill-wide like single-lane).
        # Clause-scoped (see `_iter_clauses`) rather than line-scoped so wrapping the same
        # instruction across physical lines can't change the verdict, and gated on a production
        # verb + absence of a fallback so a correct capability-conditional *presentation* sentence
        # (which legitimately uses "only if"/"if you don't have" about the tool, not the artifact)
        # doesn't get flagged as if it gated the artifact's *production*.
        conditional_loc = None
        if not delivery_exempt:
            for clause, line_no in _iter_clauses(text):
                if not any(rx.search(clause) for _tool, rx in _DELIVERY_TOOL_RES):
                    continue
                if not _DELIVERY_SKIP_OMIT_RE.search(clause):
                    continue
                if not _DELIVERY_PRODUCTION_VERB_RE.search(clause):
                    continue
                if _DELIVERY_FALLBACK_RE.search(clause):
                    continue
                conditional_loc = f"{rel}:{line_no}"
                break

        if conditional_loc:
            conditional_findings.append(_finding(
                "delivery-conditional-deliverable", SEVERITY_WARNING, TARGETS,
                f"gates the artifact itself (packaging/writing it) on a delivery tool's "
                f"availability, using a skip/omit phrase alongside a production verb and the tool "
                f"name in the same clause — e.g. the real upstream bug (anthropics/claude-code"
                f"#36438): \"only if `present_files` tool is available\" / \"If you don't, skip "
                f"this step.\" The tool call is what's conditional; producing the deliverable "
                f"never is — write/package it unconditionally, then present it with whichever "
                f"tool is available (or state the path if none is). A sentence that merely makes "
                f"*presenting* the file conditional (e.g. \"...only if such a tool is available; "
                f"otherwise state the path\") is the correct pattern and does not trip this. If a "
                f"file must use skip/omit phrasing alongside a production verb and a tool name, "
                f"mark it `portability-allow: file-delivery-tool` (file-scoped). At "
                f"{conditional_loc}.",
                conditional_loc,
            ))

    single_lane_findings = []
    named = [tool for tool, _rx in _DELIVERY_TOOL_RES if tool in skill_tool_first_loc]
    if len(named) == 1:
        named_tool = named[0]
        missing_tool = next(tool for tool, _rx in _DELIVERY_TOOL_RES if tool != named_tool)
        loc = skill_tool_first_loc[named_tool]
        single_lane_findings.append(_finding(
            "delivery-tool-single-lane", SEVERITY_WARNING, TARGETS,
            f"names the file-delivery tool `{named_tool}` but not `{missing_tool}` anywhere in "
            f"the skill — cloud and local sessions serve different delivery tools (a local session "
            f"serves `present_files`, a cloud session serves `SendUserFile`, also native to Claude "
            f"Code), and an agent only sees the one for its surface. Naming only `{named_tool}` "
            f"strands the surface served by `{missing_tool}`. "
            f"Phrase delivery by outcome, naming no tool (\"if a tool for surfacing files to the "
            f"user is available, present the file with it; if none exists, state the path\") — "
            f"naming both tools, capability-conditionally, is also acceptable and stays clean. If "
            f"a file must name only one, mark it `portability-allow: file-delivery-tool` "
            f"(file-scoped — disables both delivery-tool rules for that file). At {loc}.",
            loc,
        ))

    if md_hits_subagent:
        findings.append(_finding(
            "subagent-dependency", SEVERITY_WARNING, ["claude-ai"],
            f"references subagents at {len(md_hits_subagent)} site(s) without an 'if available' "
            f"guard — the Claude app's chat runtime has no sub-agent tool, so a skill that requires "
            f"one fails there. Check the tool list rather than the product, and keep an inline "
            f"fallback. "
            f"First: {md_hits_subagent[0]}",
            md_hits_subagent[0],
        ))
    if cli_hits:
        findings.append(_finding(
            "claude-cli-dependency", SEVERITY_WARNING, ["claude-ai"],
            f"invokes the `claude` CLI (e.g. `claude -p`) at {len(cli_hits)} site(s) — it is not on "
            f"the Claude app chat runtime's shell PATH. Gate these steps on `command -v claude` or "
            f"provide a fallback. First: {cli_hits[0]}",
            cli_hits[0],
        ))
    if browser_hits:
        findings.append(_finding(
            "browser-display-dependency", SEVERITY_WARNING, ["claude-ai", "cowork"],
            f"assumes a browser/local HTTP server at {len(browser_hits)} site(s) — neither the "
            f"Claude app's chat runtime nor a cloud or local session has a display. Provide a static / no-server "
            f"fallback. First: {browser_hits[0]}",
            browser_hits[0],
        ))
    findings += single_lane_findings
    findings += conditional_findings
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


def check_outputs_prefix(skill_path):
    """Flag skill text telling an agent to put its workspace under a relative `outputs/` path.

    A relative `outputs/x` never lands where the user looks in a cloud or local session: on older local Desktop the file
    tools' cwd was the outputs directory, so it nested a second level and dropped out of the user's
    Working-folder panel; on Desktop 2.7032.0 and later the file tools refuse any relative path; in
    a cloud session it resolves under the working directory, which the user cannot see until the file
    is delivered. Scans
    instruction text only — a script's own relative path is a different problem, covered by the
    absolute-path guidance in references/environments.md.
    """
    findings = []
    for p in _iter_text_files(skill_path):
        try:
            text = p.read_text()
        except OSError:
            continue
        if _OUTPUTS_ALLOW_RE.search(text):
            continue
        rel = p.relative_to(skill_path)
        for n, line in enumerate(text.split("\n"), 1):
            m = _OUTPUTS_WORKSPACE_RE.search(line)
            if not m:
                continue
            loc = f"{rel}:{n}"
            findings.append(_finding(
                "outputs-prefix-relative", SEVERITY_WARNING, ["cowork"],
                f"instructs a workspace at the relative path `{m.group(0)}` — in a cloud or local session no relative "
                f"form of this is reliably delivered: a FILE TOOL refuses it on Desktop 2.7032.0 and "
                f"later, nested it to `outputs/outputs/...` (out of the user's Working-folder panel) "
                f"on older Desktop, and in a cloud session it lands outside `/mnt/user-data/outputs`, "
                f"undelivered where that is the delivery folder; under the SHELL it resolves against the "
                f"session root, invisible to the user and unreachable by the file tools. Fix: use "
                f"the absolute path of the directory the surface's instructions designate for work "
                f"(in a local session the outputs directory, not the private \"Primary working "
                f"directory\"; in a cloud session usually the working directory), in the form "
                f"each tool family accepts (locally the shell spells it `/sessions/<id>/mnt/outputs/`; "
                f"elsewhere the two forms coincide), and hand sub-agents both forms, labelled. A documented absolute "
                f"`.../mnt/outputs/...` path does not trip this. Suppress per file with an HTML-"
                f"comment `<!-- portability-allow: outputs-prefix -->`. At {loc}.",
                loc,
            ))
            break
    return findings


# ---- relative-output-path -----------------------------------------------------------------
# An instruction to WRITE a file to a bare relative path. Where that lands depends on the runtime's
# working directory: the project in Claude Code (visible, which is why this skips that target), a
# private working directory in a cloud session, a refusal from a local session's file tools, a work dir
# separate from the outputs directory on the chat runtime. Precision over recall — the rule fires
# only on an imperative write verb with a relative FILE path (a known deliverable extension), and
# skips anything an author has already anchored; RelativeOutputPathTests pins each exclusion.
_REL_OUT_EXT = (r"(?:md|markdown|txt|json|jsonl|csv|tsv|html?|pdf|docx|xlsx|pptx|png|jpe?g|svg|"
                r"ya?ml|xml|zip)")
# Not preceded by a path/variable/placeholder character, so `/abs/x.md`, `~/x.md`, `$D/x.md`,
# `<ws>/x.md`, `{d}/x.md` and `https://h/x.md` never yield a relative match.
_REL_OUT_PATH = (r"(?<![\w/~$<>{}.\-@:])(?P<path>(?:\./)?(?:[A-Za-z0-9_][\w.\-]*/)*"
                 r"[A-Za-z0-9_][\w\-]*(?:\.[\w\-]+)*\." + _REL_OUT_EXT + r")(?![\w/<{])")
# The verb must sit where an imperative does — line/list start, after sentence punctuation or bold,
# or after a modal/connective — so nouns ("the export", "sub-agent output") and descriptions of
# what a script does ("the viewer saves ...") don't count.
_REL_OUT_VERB = (r"(?:^\s*(?:[-*+>]\s+|\d+[.)]\s+)?|[.!?:;]\s+|\*\*|"
                 r"\b(?:then|and|also|to|should|must|please|always|you|now)\s+)"
                 r"(?:write|save|create|output|export|store|dump|generate|produce)\b")
_REL_OUT_OPEN = r"[`'\"*]*"
# "save the report to report.md" — destination after to/into/as, within one clause.
_REL_OUT_DEST_RE = re.compile(
    _REL_OUT_VERB + r"[^.!?\n`]{0,60}?\b(?:to|into|as)\s+" + _REL_OUT_OPEN + _REL_OUT_PATH,
    re.IGNORECASE,
)
# "create ./out/table.csv" — direct object, only when it has a directory part ("Create
# benchmark.json" names a file kind far more often than it places one).
_REL_OUT_OBJ_RE = re.compile(
    _REL_OUT_VERB + r"\s+(?:the\s+)?(?:file\s+)?" + _REL_OUT_OPEN + r"(?=[^\s`'\"*]*/)"
    + _REL_OUT_PATH,
    re.IGNORECASE,
)
# The skill's own bundle, and config files that belong to a project or plugin, not a deliverable.
_REL_OUT_BUNDLED = ("scripts/", "references/", "assets/", "agents/", "evals/")
_REL_OUT_OWN = frozenset({
    "SKILL.md", "README.md", "CHANGELOG.md", "CLAUDE.md", "AGENTS.md", "LICENSE.txt",
    "plugin.json", "marketplace.json", "hooks.json", "settings.json", "settings.local.json",
})
# A line that names the base explicitly ("relative to", "in the run directory") is anchored.
_REL_OUT_BASE_RE = re.compile(
    r"\brelative to\b|\b(?:under|inside|within|in|into)\s+(?:the|each|your|its|that|this)\s+"
    r"[\w`<>/.\-]*\s*(?:dir|directory|folder|workspace|run dir|outputs?)\b",
    re.IGNORECASE,
)
_REL_OUT_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_REL_OUT_CD_ABS_RE = re.compile(r"\bcd\s+[\"']?(?:/|~|\$|<)")
# Same form and reasoning as _OUTPUTS_ALLOW_RE: an HTML comment only.
_REL_OUT_ALLOW_RE = re.compile(r"<!--\s*portability-allow:\s*relative-output-path\s*-->")


def _rel_out_anchored_elsewhere(text, basename):
    """True if the file also spells this basename under an absolute/variable/placeholder base."""
    return re.search(
        r"(?:^|(?<=[\s`'\"(=]))(?:/|~/|\$\{?\w+\}?/|<[^>\n]+>/|\{[^}\s]+\}/)(?:[^\s`'\"]*/)?"
        + re.escape(basename) + r"(?![\w.])",
        text, re.MULTILINE,
    ) is not None


def _rel_out_match(line):
    for rx in (_REL_OUT_DEST_RE, _REL_OUT_OBJ_RE):
        for m in rx.finditer(line):
            path = m.group("path")
            bare = path[2:] if path.startswith("./") else path
            if bare.startswith(_REL_OUT_BUNDLED) or bare.rsplit("/", 1)[-1] in _REL_OUT_OWN:
                continue
            if re.match(r"[A-Z][A-Z0-9_]*/", bare):  # `OUT_DIR/x.md` — a variable, not a path
                continue
            if line[max(0, m.start("path") - 2):m.start("path")] == "](":  # markdown link target
                continue
            return path
    return None


def check_relative_output_path(skill_path):
    """Flag SKILL.md / references text that writes a file to a bare relative path.

    Advisory: the relative form is correct in Claude Code, and a skill may define its base
    elsewhere in a way no line-level check can see. Silent on any line `outputs-prefix-relative`
    already owns, so the two never double-fire.
    """
    findings = []
    files = [skill_path / "SKILL.md"]
    ref_dir = skill_path / "references"
    if ref_dir.is_dir():
        files += sorted(ref_dir.rglob("*.md"))
    for p in files:
        try:
            text = p.read_text()
        except OSError:
            continue
        if _REL_OUT_ALLOW_RE.search(text):
            continue
        lines = text.split("\n")
        # A fenced block that `cd`s to an absolute/variable dir first is a worked shell example
        # whose relative paths have a stated base.
        skip, start = set(), None
        for n, line in enumerate(lines):
            if _REL_OUT_FENCE_RE.match(line):
                if start is None:
                    start = n
                else:
                    if _REL_OUT_CD_ABS_RE.search("\n".join(lines[start:n + 1])):
                        skip.update(range(start, n + 1))
                    start = None
        rel = p.relative_to(skill_path)
        for n, line in enumerate(lines):
            if n in skip or _REL_OUT_BASE_RE.search(line) or _OUTPUTS_WORKSPACE_RE.search(line):
                continue
            path = _rel_out_match(line)
            if not path or _rel_out_anchored_elsewhere(text, path.rsplit("/", 1)[-1]):
                continue
            loc = f"{rel}:{n + 1}"
            findings.append(_finding(
                "relative-output-path", SEVERITY_ADVISORY, ["claude-ai", "cowork"],
                f"tells the model to write `{path}` by a bare relative path. Where that lands "
                f"depends on the runtime's working directory: invisible to the user in a cloud "
                f"session, refused by a local session's file tools, outside the outputs directory on "
                f"the chat runtime (only Claude Code's project directory makes it visible). Write "
                f"deliverables by ABSOLUTE path to the directory the session's instructions "
                f"designate, then deliver them to the user; for scratch files, state the base "
                f"directory. Suppress per file with an HTML comment "
                f"`<!-- portability-allow: relative-output-path -->`. At {loc}.",
                loc,
            ))
            break
    return findings


def check_thirdparty_imports(skill_path):
    """Flag bundled-script imports that Cowork's image does not already provide.

    Modules in `COWORK_PREINSTALLED` are silent — the image ships them, so importing one is not a
    portability risk. Anything else is ADVISORY, not a warning: the sandbox pip-installed an absent
    package from PyPI successfully in the probed configuration, so the hard failure this rule once
    predicted does not occur there. What remains is per-run install latency, plus the fact that
    egress is org-configurable and a locked-down org can deny it.
    """
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
                if (root and root not in stdlib and root not in local_mods
                        and root not in COWORK_PREINSTALLED and root not in offenders):
                    offenders[root] = f"{rel}:{lineno}"
    for mod, loc in sorted(offenders.items()):
        findings.append(_finding(
            "thirdparty-import", SEVERITY_ADVISORY, ["cowork"],
            f"bundled script imports third-party module `{mod}`, which is not in the Python stack "
            f"confirmed preinstalled in the local session's image — so the skill pays a `pip install` on "
            f"every run there. The sandbox installed an absent package from PyPI successfully in the probed "
            f"configuration, but egress is org-configurable and a locked-down org can deny it, in "
            f"which case this step fails. Prefer the preinstalled stack where it suffices (numpy, "
            f"pandas, requests, PyYAML, bs4, openpyxl, Pillow, matplotlib, python-docx, "
            f"python-pptx), and degrade gracefully otherwise. At {loc}.",
            loc,
        ))
    return findings


def lint_portability(skill_path):
    """Return (all_findings, structural_error_or_None)."""
    skill_path = Path(skill_path)
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return [], "SKILL.md not found"
    skill_md_text = skill_md.read_text()
    fields = parse_frontmatter(skill_md_text)
    findings = []
    findings += check_description_length(fields)
    findings += check_compaction_budget(skill_md_text)
    findings += check_combined_compaction_budget(skill_path)
    findings += check_plugin_bin_directory(skill_path)
    findings += check_runtime_constructs(skill_path)
    findings += check_outputs_prefix(skill_path)
    findings += check_relative_output_path(skill_path)
    findings += check_thirdparty_imports(skill_path)
    return findings, None


def _filter_by_target(findings, target):
    if target == "all":
        return findings
    return [f for f in findings if target in f["targets"]]


def main():
    parser = argparse.ArgumentParser(
        description="Lint a skill for cross-runtime portability (Claude Code / the Claude app's chat "
                    "runtime / the Claude app's cloud and local sessions).",
        epilog=(
            "Examples:\n"
            "  python -m scripts.check_portability ./my-skill\n"
            "  python -m scripts.check_portability --target claude-ai ./my-skill\n"
            "  python -m scripts.check_portability --json --strict ./my-skill\n"
            "\n"
            "Targets: claude-code | claude-ai | cowork | all (default: all)\n"
            "  claude-ai  the Claude app's chat runtime\n"
            "  cowork     sandboxed cloud and local sessions; the id predates the merge\n"
            "\n"
            "Exit codes:\n"
            "  0  no gating findings (advisories always report without gating)\n"
            "  1  a finding gates: an over-cap description (always), or a warning/error under\n"
            "     --strict (add --strict-advisories to gate on advisories too)\n"
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
                        help="Exit 1 if any warning/error finding is reported for the selected target")
    parser.add_argument("--strict-advisories", action="store_true",
                        help="With --strict, also gate on advisory-severity findings "
                             "(default: advisories are reported but never gate)")
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
    gateable = [f for f in shown
                if args.strict_advisories or f["severity"] != SEVERITY_ADVISORY]
    gate = has_hard_error or (args.strict and len(gateable) > 0)

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
                  + ("gating (over-cap description, or a warning under --strict)."
                     if gate else "non-gating — exit 0. Use --strict to gate on warnings."))
    sys.exit(1 if gate else 0)


if __name__ == "__main__":
    main()
