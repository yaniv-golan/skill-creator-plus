#!/usr/bin/env python3
"""
Skill Packager - Creates a distributable .skill file of a skill folder
"""

import argparse
import fnmatch
import json
import sys
import zipfile
from pathlib import Path
from scripts.quick_validate import validate_skill

# Patterns to exclude when packaging skills.
EXCLUDE_DIRS = {"__pycache__", "node_modules"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store"}
# Directories excluded only at the skill root (not when nested deeper).
ROOT_EXCLUDE_DIRS = {"evals"}


def should_exclude(rel_path: Path) -> bool:
    """Check if a path should be excluded from packaging."""
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    # rel_path is relative to skill_path.parent, so parts[0] is the skill
    # folder name and parts[1] (if present) is the first subdir.
    if len(parts) > 1 and parts[1] in ROOT_EXCLUDE_DIRS:
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def _plan_files(skill_path: Path) -> tuple[list[Path], list[Path]]:
    """Walk the skill directory and split files into (included, skipped) by relative path."""
    included: list[Path] = []
    skipped: list[Path] = []
    for file_path in skill_path.rglob("*"):
        if not file_path.is_file():
            continue
        arcname = file_path.relative_to(skill_path.parent)
        if should_exclude(arcname):
            skipped.append(arcname)
        else:
            included.append(arcname)
    return included, skipped


def package_skill(skill_path, output_dir=None, dry_run=False, as_json=False):
    """
    Package a skill folder into a .skill file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory (defaults to skill's parent)
        dry_run: If True, plan but don't write the zip
        as_json: If True, emit a JSON result on stdout instead of prose

    Returns:
        Path to the created .skill file (or planned path on dry-run), or None on error.
    """
    skill_path = Path(skill_path).resolve()

    def _emit_error(msg: str) -> None:
        if as_json:
            json.dump({"ok": False, "error": msg, "output": None, "files": [], "skipped": []}, sys.stdout)
            print()
        else:
            print(f"Error: {msg}", file=sys.stderr)

    # Validate skill folder exists
    if not skill_path.exists():
        _emit_error(f"Skill folder not found: {skill_path}")
        return None
    if not skill_path.is_dir():
        _emit_error(f"Path is not a directory: {skill_path}")
        return None
    if not (skill_path / "SKILL.md").exists():
        _emit_error(f"SKILL.md not found in {skill_path}")
        return None

    # Run validation before packaging
    valid, message = validate_skill(skill_path)
    if not valid:
        _emit_error(f"Validation failed: {message}. Fix the errors before packaging.")
        return None

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        if not dry_run:
            output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = skill_path.parent

    skill_filename = output_path / f"{skill_name}.skill"

    included, skipped = _plan_files(skill_path)

    if dry_run:
        if as_json:
            json.dump(
                {
                    "ok": True,
                    "dry_run": True,
                    "output": str(skill_filename),
                    "files": [str(p) for p in included],
                    "skipped": [str(p) for p in skipped],
                },
                sys.stdout,
            )
            print()
        else:
            print(f"[dry-run] Would package skill to: {skill_filename}")
            print(f"[dry-run] {len(included)} file(s) would be included:")
            for p in included:
                print(f"  + {p}")
            if skipped:
                print(f"[dry-run] {len(skipped)} file(s) would be skipped:")
                for p in skipped:
                    print(f"  - {p}")
        return skill_filename

    # Warn before clobbering an existing artifact.
    if skill_filename.exists() and not as_json:
        print(f"Note: Overwriting existing artifact at {skill_filename}", file=sys.stderr)

    try:
        with zipfile.ZipFile(skill_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            for arcname in included:
                source = skill_path.parent / arcname
                zipf.write(source, arcname)
    except Exception as e:
        _emit_error(f"Failed to create .skill file: {e}")
        return None

    if as_json:
        json.dump(
            {
                "ok": True,
                "dry_run": False,
                "output": str(skill_filename),
                "files": [str(p) for p in included],
                "skipped": [str(p) for p in skipped],
            },
            sys.stdout,
        )
        print()
    else:
        print(f"Packaged skill to: {skill_filename}")
        print(f"  {len(included)} file(s) included, {len(skipped)} skipped")
    return skill_filename


def main():
    parser = argparse.ArgumentParser(
        description="Package a skill folder into a distributable .skill file (zip).",
        epilog=(
            "Examples:\n"
            "  python -m scripts.package_skill ./my-skill\n"
            "  python -m scripts.package_skill ./my-skill ./dist\n"
            "  python -m scripts.package_skill --dry-run ./my-skill\n"
            "  python -m scripts.package_skill --json ./my-skill\n"
            "\n"
            "Exit codes:\n"
            "  0  packaging succeeded (or dry-run completed)\n"
            "  1  packaging failed (skill not found, validation failed, or zip error)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("skill_path", help="Path to the skill folder to package")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Optional output directory for the .skill file (defaults to the skill's parent)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the file list and output path; do not write the .skill zip",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout instead of prose",
    )
    args = parser.parse_args()

    result = package_skill(
        args.skill_path,
        args.output_dir,
        dry_run=args.dry_run,
        as_json=args.json,
    )
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
