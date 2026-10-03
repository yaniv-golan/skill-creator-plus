"""What packaging leaves out of a .skill archive.

Shared by package_skill (which applies it) and quick_validate (which must judge a skill by what will
actually ship). Kept in its own module because package_skill imports quick_validate, so the reverse
import would be circular.
"""

import fnmatch
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", "node_modules"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store"}
# Directories excluded only at the skill root (not when nested deeper).
ROOT_EXCLUDE_DIRS = {"evals", "tests"}


def should_exclude(rel_path: Path) -> bool:
    """True if packaging leaves this path out.

    rel_path is relative to the skill folder's PARENT, so parts[0] is the skill folder name and
    parts[1] (if present) is the first directory inside it.
    """
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    if len(parts) > 1 and parts[1] in ROOT_EXCLUDE_DIRS:
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def shipped_files(skill_path: Path):
    """Yield (path, rel_path) for every file packaging would include. Symlinks are never followed."""
    skill_path = Path(skill_path)
    for file_path in skill_path.rglob("*"):
        if file_path.is_symlink() or not file_path.is_file():
            continue
        rel = file_path.relative_to(skill_path.parent)
        if not should_exclude(rel):
            yield file_path, rel
