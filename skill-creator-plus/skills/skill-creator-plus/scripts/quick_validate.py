#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import sys
import os
import re
import yaml
from pathlib import Path

def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    content = skill_md.read_text()
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    # Portable spec fields: name, description, license, compatibility, metadata, allowed-tools
    # Claude-specific documented fields: when_to_use, model, effort, agent, context,
    #   disable-model-invocation, user-invocable, argument-hint, paths, hooks, shell
    # Undocumented-but-functional: arguments, version (top-level), created_by
    ALLOWED_PROPERTIES = {
        # Portable
        'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools',
        # Claude-specific
        'when_to_use', 'model', 'effort', 'agent', 'context',
        'disable-model-invocation', 'user-invocable', 'argument-hint',
        'paths', 'hooks', 'shell',
        # Undocumented-but-functional
        'arguments', 'version', 'created_by',
    }

    # Check for unexpected properties (excluding nested keys under metadata)
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    if 'name' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract name for validation
    name = frontmatter.get('name', '')
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        # Check naming convention (kebab-case: lowercase with hyphens)
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, f"Name '{name}' should be kebab-case (lowercase letters, digits, and hyphens only)"
        if name.startswith('-') or name.endswith('-') or '--' in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        # Check name length (max 64 characters per spec)
        if len(name) > 64:
            return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."

    # Extract and validate description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        # Check for angle brackets
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"
        # Check description length (max 1024 characters per spec)
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."

    # Validate compatibility field if present (optional)
    compatibility = frontmatter.get('compatibility', '')
    if compatibility:
        if not isinstance(compatibility, str):
            return False, f"Compatibility must be a string, got {type(compatibility).__name__}"
        if len(compatibility) > 500:
            return False, f"Compatibility is too long ({len(compatibility)} characters). Maximum is 500 characters."

    # Validate context field if present — only 'fork' is a supported value
    context = frontmatter.get('context')
    if context is not None:
        if context != 'fork':
            return False, f"'context' must be 'fork' (got '{context}'). Only 'context: fork' is supported."

    # Validate disable-model-invocation field if present — must be a boolean
    disable_invocation = frontmatter.get('disable-model-invocation')
    if disable_invocation is not None:
        if not isinstance(disable_invocation, bool):
            return False, f"'disable-model-invocation' must be a boolean (true or false), got '{disable_invocation}'"

    # Validate user-invocable field if present — must be a boolean
    user_invocable = frontmatter.get('user-invocable')
    if user_invocable is not None:
        if not isinstance(user_invocable, bool):
            return False, f"'user-invocable' must be a boolean (true or false), got '{user_invocable}'"

    # Validate argument-hint field if present — must be a short string
    argument_hint = frontmatter.get('argument-hint')
    if argument_hint is not None:
        if not isinstance(argument_hint, str):
            return False, f"'argument-hint' must be a string, got {type(argument_hint).__name__}"
        if len(argument_hint) > 200:
            return False, f"'argument-hint' is too long ({len(argument_hint)} characters). Maximum is 200 characters."

    # when_to_use — Claude-specific companion to description; joined with it in the skill listing
    when_to_use_raw = frontmatter.get('when_to_use')
    when_to_use = ''
    if when_to_use_raw is not None:
        if not isinstance(when_to_use_raw, str):
            return False, f"'when_to_use' must be a string, got {type(when_to_use_raw).__name__}"
        when_to_use = when_to_use_raw.strip()
        if '<' in when_to_use or '>' in when_to_use:
            return False, "when_to_use cannot contain angle brackets (< or >)"

    # Combined listing entry cap (Claude v2.1.116): description + when_to_use truncates at 1,536 chars.
    # Both are stripped first so the measurement matches what Claude's listing actually renders.
    combined_len = len(description or '') + len(when_to_use)
    if combined_len > 1536:
        return False, (
            f"description + when_to_use combined is {combined_len} chars. "
            f"Claude Code truncates skill listing entries at 1536 chars — trim one or both."
        )

    # effort — keyword or integer (Claude-specific)
    effort = frontmatter.get('effort')
    if effort is not None:
        allowed_effort = {'low', 'medium', 'high', 'xhigh', 'max'}
        if isinstance(effort, str):
            if effort not in allowed_effort:
                return False, (
                    f"'effort' must be one of {sorted(allowed_effort)} or an integer, got '{effort}'"
                )
        elif not isinstance(effort, int) or isinstance(effort, bool):
            return False, f"'effort' must be a string keyword or integer, got {type(effort).__name__}"

    # model — string alias or 'inherit' (Claude-specific)
    model = frontmatter.get('model')
    if model is not None and not isinstance(model, str):
        return False, f"'model' must be a string, got {type(model).__name__}"

    # agent — subagent type (Claude-specific; meaningful when context: fork)
    agent = frontmatter.get('agent')
    if agent is not None and not isinstance(agent, str):
        return False, f"'agent' must be a string, got {type(agent).__name__}"

    # paths — gitignore-syntax patterns (Claude-specific; docs say "glob" but impl is gitignore)
    paths = frontmatter.get('paths')
    if paths is not None:
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            return False, "'paths' must be a list of strings (gitignore-syntax patterns)"

    # hooks — object keyed by PreToolUse/PostToolUse (Claude-specific)
    hooks = frontmatter.get('hooks')
    if hooks is not None and not isinstance(hooks, dict):
        return False, f"'hooks' must be an object (PreToolUse/PostToolUse keys), got {type(hooks).__name__}"

    # shell — { interpreter: bash | powershell } (Claude-specific)
    shell = frontmatter.get('shell')
    if shell is not None:
        if not isinstance(shell, dict):
            return False, f"'shell' must be an object, got {type(shell).__name__}"
        interpreter = shell.get('interpreter')
        if interpreter is not None and interpreter not in {'bash', 'powershell'}:
            return False, f"'shell.interpreter' must be 'bash' or 'powershell', got '{interpreter}'"

    # version — top-level informational (separate from metadata.version)
    version_field = frontmatter.get('version')
    if version_field is not None and not isinstance(version_field, (str, int, float)):
        return False, f"'version' must be a string or number, got {type(version_field).__name__}"

    # arguments — undocumented but functional: space-separated named args mapped positionally
    arguments = frontmatter.get('arguments')
    if arguments is not None and not isinstance(arguments, str):
        return False, f"'arguments' must be a space-separated string, got {type(arguments).__name__}"

    # created_by — informational
    created_by = frontmatter.get('created_by')
    if created_by is not None and not isinstance(created_by, str):
        return False, f"'created_by' must be a string, got {type(created_by).__name__}"

    return True, "Skill is valid!"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)
    
    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)