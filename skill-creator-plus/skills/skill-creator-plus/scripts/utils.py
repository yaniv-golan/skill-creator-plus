"""Shared utilities for skill-creator scripts."""

import re
from pathlib import Path



def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    """Parse a SKILL.md file, returning (name, description, full_content)."""
    content = (skill_path / "SKILL.md").read_text()
    lines = content.split("\n")

    if lines[0].strip() != "---":
        raise ValueError("SKILL.md missing frontmatter (no opening ---)")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("SKILL.md missing frontmatter (no closing ---)")

    name = ""
    description = ""
    frontmatter_lines = lines[1:end_idx]
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if line.startswith("name:"):
            name = line[len("name:"):].strip().strip('"').strip("'")
        elif line.startswith("description:"):
            value = line[len("description:"):].strip()
            # Handle YAML multiline indicators (>, |, >-, |-)
            if value in (">", "|", ">-", "|-"):
                continuation_lines: list[str] = []
                i += 1
                while i < len(frontmatter_lines) and (frontmatter_lines[i].startswith("  ") or frontmatter_lines[i].startswith("\t")):
                    continuation_lines.append(frontmatter_lines[i].strip())
                    i += 1
                description = " ".join(continuation_lines)
                continue
            else:
                description = value.strip('"').strip("'")
        i += 1

    return name, description, content


class DotenvError(Exception):
    """Dotenv file could not be read or parsed.

    The message carries a line number only, never line content: the file holds secrets.
    """


_INLINE_COMMENT = re.compile(r"\s#")


def load_credentials_from_dotenv(path, names) -> dict[str, str]:
    """Return {name: value} for the wanted keys found in a dotenv file.

    Pure parser: does not read or modify os.environ. Only lines whose key is in
    `names` are inspected; all others are skipped (so multi-line values for other
    keys cannot break it). Last occurrence wins; an empty value counts as absent.
    Raises DotenvError (line number only, no content) on IO or parse errors.
    """
    wanted = set(names)
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        raise DotenvError(f"cannot read dotenv file ({type(e).__name__})") from None
    text = raw.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]

    found: dict[str, str] = {}
    for lineno, line in enumerate(text.split("\n"), start=1):
        line = line.rstrip("\r").lstrip()
        if line.startswith("export") and line[6:7] in (" ", "\t"):
            line = line[6:].lstrip()
        key, eq, rest = line.partition("=")
        key = key.strip()
        if not eq or key not in wanted:
            continue
        value = rest.lstrip()
        if value[:1] in ("'", '"'):
            quote = value[0]
            end = value.find(quote, 1)
            if end == -1:
                raise DotenvError(f"line {lineno}: unterminated quote")
            tail = value[end + 1:].strip()
            if tail and not tail.startswith("#"):
                raise DotenvError(f"line {lineno}: unexpected text after closing quote")
            value = value[1:end]
        else:
            m = _INLINE_COMMENT.search(rest)
            value = (rest[:m.start()] if m else rest).strip()
        if value:
            found[key] = value
        else:
            found.pop(key, None)
    return found
