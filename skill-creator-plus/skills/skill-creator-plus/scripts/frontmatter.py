#!/usr/bin/env python3
"""
Stdlib-only parser for SKILL.md YAML frontmatter.

Why this exists: skill-creator-plus is distributed as a `.skill` zip and runs in sandboxes
(Cowork's container, Claude.ai) that do NOT ship PyYAML and cannot `pip install` it (default-deny
egress). Depending on PyYAML made `quick_validate.py` / `package_skill.py` crash there. Frontmatter
is a small, well-constrained YAML subset — a mapping of scalars, string lists, and shallow nested
mappings — so we parse it with the standard library instead of a full YAML engine.

Scope (what real SKILL.md frontmatter uses, and all this parser supports):
  - block mappings, nested by indentation (e.g. `metadata: { requires: { bins: [] } }`)
  - block sequences (`- item`) and flow sequences (`[a, b]`, `[]`)
  - flow mappings only in their empty form (`{}`)
  - scalars: plain / single- / double-quoted strings, booleans, null, ints, floats
  - block scalars (`|`, `>`, with `-`/`+` chomping)
  - `# comments` on unquoted lines

Deliberately UNSUPPORTED — raises FrontmatterError with a clear message rather than guessing:
  anchors (`&`), aliases (`*`), tags (`!`), merge keys (`<<`), multi-document streams, and
  non-empty flow mappings. Exotic YAML in frontmatter is itself a portability smell — other
  runtimes' parsers may choke on it too — so rejecting it is a feature, not a limitation.

The public entry point is `parse(text)`; it returns the same shape `yaml.safe_load` would for the
supported subset (verified by a differential test against PyYAML over the repo's real fixtures).
"""

import re

__all__ = ["parse", "FrontmatterError"]


class FrontmatterError(ValueError):
    """Raised for invalid or unsupported frontmatter YAML."""


_BOOL_TRUE = {"true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON"}
_BOOL_FALSE = {"false", "False", "FALSE", "no", "No", "NO", "off", "Off", "OFF"}
_NULL = {"", "~", "null", "Null", "NULL"}
_INT_RE = re.compile(r"^[-+]?[0-9]+$")
_FLOAT_RE = re.compile(r"^[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?$")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _strip_comment(s):
    """Remove a trailing ` # comment` from an unquoted scalar (whitespace-preceded #)."""
    in_s = in_d = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and i > 0 and s[i - 1] in " \t":
            return s[:i].rstrip()
    return s.rstrip()


def _scalar(token):
    """Resolve a plain/quoted scalar token to a Python value, matching YAML 1.1 core resolution."""
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] == '"':
        return _unescape_double(token[1:-1])
    if len(token) >= 2 and token[0] == token[-1] == "'":
        return token[1:-1].replace("''", "'")
    token = _strip_comment(token)
    if token in _NULL:
        return None
    if token in _BOOL_TRUE:
        return True
    if token in _BOOL_FALSE:
        return False
    if _INT_RE.match(token):
        return int(token)
    if _FLOAT_RE.match(token) and any(c in token for c in ".eE"):
        try:
            return float(token)
        except ValueError:
            pass
    return token


def _unescape_double(s):
    out, i = [], 0
    simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(simple.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _reject_unsupported(raw_line, stripped):
    if stripped.startswith(("&", "*", "!")):
        raise FrontmatterError(
            "unsupported YAML construct (anchor/alias/tag) in frontmatter — keep frontmatter simple"
        )
    if stripped.startswith("<<"):
        raise FrontmatterError("unsupported YAML merge key (<<) in frontmatter")
    if stripped in ("---", "...") :
        raise FrontmatterError("multi-document YAML is not supported in frontmatter")
    if stripped.startswith("{") and stripped.strip() not in ("{}",):
        raise FrontmatterError("non-empty flow mappings ({a: b}) are not supported in frontmatter")


def _parse_flow_sequence(token):
    inner = token[1:-1].strip()
    if not inner:
        return []
    # split on commas not inside quotes
    parts, buf, in_s, in_d = [], [], False, False
    for ch in inner:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        if ch == "," and not in_s and not in_d:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [_scalar(p) for p in parts]


def _value_from_inline(token):
    """A value that appears on the same line as its key (after `key:`)."""
    token = token.strip()
    if token[:1] in ("&", "*", "!"):
        raise FrontmatterError(
            "unsupported YAML construct (anchor/alias/tag) in frontmatter value — keep it simple"
        )
    if token.startswith("[") and token.endswith("]"):
        return _parse_flow_sequence(token)
    if token == "{}":
        return {}
    if token.startswith("{"):
        raise FrontmatterError("non-empty flow mappings ({a: b}) are not supported in frontmatter")
    return _scalar(token)


def _skip_blank(lines, i):
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s.startswith("#"):
            i += 1
        else:
            return i
    return i


def _block_scalar(lines, i, parent_indent, indicator):
    """Collect a `|` / `>` block scalar; lines indented deeper than the parent key.

    Matches PyYAML chomping: clip (default) keeps a single trailing newline ONLY when the block is
    followed by a line break (another key, or a source newline) — not at true end-of-text; strip
    (`-`) never keeps one; keep (`+`) preserves trailing blanks.
    """
    fold = indicator[0] == ">"
    chomp = indicator[1] if len(indicator) > 1 else ""
    collected = []
    block_indent = None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            collected.append("")
            i += 1
            continue
        ind = _indent(line)
        if ind <= parent_indent:
            break
        if block_indent is None:
            block_indent = ind
        collected.append(line[block_indent:] if len(line) >= block_indent else line.lstrip(" "))
        i += 1
    followed_by_break = (i < len(lines)) or (bool(collected) and collected[-1] == "")
    body = collected[:]
    while body and body[-1] == "":
        body.pop()
    text = (" " if fold else "\n").join(body)
    if chomp == "-":
        pass  # strip
    elif chomp == "+":
        trailing = len(collected) - len(body)
        if body:
            text += "\n" * max(1, trailing)
    elif body and followed_by_break:  # clip (default)
        text += "\n"
    return text, i


def _parse_block(lines, i, indent):
    """Parse a mapping or sequence whose items are at column `indent`. Returns (value, next_i)."""
    i = _skip_blank(lines, i)
    if i >= len(lines):
        return None, i
    first = lines[i]
    stripped = first.strip()
    if stripped == "- " or stripped == "-" or stripped.startswith("- "):
        return _parse_sequence(lines, i, indent)
    return _parse_mapping(lines, i, indent)


def _parse_mapping(lines, i, indent):
    result = {}
    while i < len(lines):
        i = _skip_blank(lines, i)
        if i >= len(lines):
            break
        line = lines[i]
        cur = _indent(line)
        if cur < indent:
            break
        if cur > indent:
            raise FrontmatterError(f"unexpected indentation in frontmatter at line: {line!r}")
        stripped = line.strip()
        _reject_unsupported(line, stripped)
        m = re.match(r"^([^:\s][^:]*?):(\s+(.*))?$", stripped)
        if not m:
            raise FrontmatterError(f"could not parse frontmatter line: {line!r}")
        key = m.group(1).strip()
        if (key[0] == key[-1] and key[0] in "\"'") and len(key) >= 2:
            key = key[1:-1]
        rest = (m.group(3) or "").strip()
        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            value, i = _block_scalar(lines, i + 1, indent, rest)
        elif rest == "":
            j = _skip_blank(lines, i + 1)
            if j < len(lines) and _indent(lines[j]) > indent:
                value, i = _parse_block(lines, j, _indent(lines[j]))
            else:
                value = None
                i += 1
        else:
            value = _value_from_inline(rest)
            i += 1
        result[key] = value
    return result, i


def _parse_sequence(lines, i, indent):
    items = []
    while i < len(lines):
        i = _skip_blank(lines, i)
        if i >= len(lines):
            break
        line = lines[i]
        cur = _indent(line)
        if cur < indent:
            break
        if cur > indent:
            raise FrontmatterError(f"unexpected indentation in sequence at line: {line!r}")
        stripped = line.strip()
        if not (stripped == "-" or stripped.startswith("- ")):
            break
        rest = stripped[1:].strip()
        if rest == "":
            j = _skip_blank(lines, i + 1)
            if j < len(lines) and _indent(lines[j]) > indent:
                value, i = _parse_block(lines, j, _indent(lines[j]))
            else:
                value = None
                i += 1
        else:
            value = _value_from_inline(rest)
            i += 1
        items.append(value)
    return items, i


def parse(text):
    """Parse frontmatter YAML text (the content between the `---` fences).

    Returns a dict (or other value for the supported subset). Raises FrontmatterError on invalid
    or unsupported input, mirroring how `yaml.safe_load` would raise yaml.YAMLError.
    """
    if text is None:
        return None
    lines = text.split("\n")
    i = _skip_blank(lines, 0)
    if i >= len(lines):
        return None
    value, _ = _parse_block(lines, i, _indent(lines[i]))
    return value
