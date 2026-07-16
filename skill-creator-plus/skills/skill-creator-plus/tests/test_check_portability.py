import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from check_portability import (  # noqa: E402
    parse_frontmatter,
    lint_portability,
    check_thirdparty_imports,
    _filter_by_target,
    DESC_HARD_CAP,
)


def _skill(tmp: Path, frontmatter: str, body: str = "Body.\n") -> Path:
    d = tmp / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}")
    return d


def _rules(findings):
    return {f["rule"] for f in findings}


class FrontmatterParserTests(unittest.TestCase):
    def test_simple_scalars_and_quotes(self):
        fm = parse_frontmatter('---\nname: my-skill\ndescription: "hello world"\n---\n')
        self.assertEqual(fm["name"], "my-skill")
        self.assertEqual(fm["description"], "hello world")

    def test_block_scalar(self):
        text = "---\nname: x\ndescription: |\n  line one\n  line two\n---\n"
        fm = parse_frontmatter(text)
        self.assertIn("line one", fm["description"])
        self.assertIn("line two", fm["description"])

    def test_no_frontmatter(self):
        self.assertEqual(parse_frontmatter("# just a heading\n"), {})


class DescriptionLengthTests(unittest.TestCase):
    def test_over_hard_cap_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), f"name: x\ndescription: {'a' * (DESC_HARD_CAP + 10)}")
            findings, err = lint_portability(skill)
            self.assertIsNone(err)
            over = [f for f in findings if f["rule"] == "desc-over-hard-cap"]
            self.assertEqual(len(over), 1)
            self.assertEqual(over[0]["severity"], "error")

    def test_combined_cap_warning(self):
        with tempfile.TemporaryDirectory() as td:
            fm = f"name: x\ndescription: {'a' * 900}\nwhen_to_use: {'b' * 700}"
            skill = _skill(Path(td), fm)
            findings, _ = lint_portability(skill)
            self.assertIn("listing-entry-truncation", _rules(findings))

    def test_short_description_clean(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: A concise, useful description.")
            findings, _ = lint_portability(skill)
            self.assertNotIn("desc-over-hard-cap", _rules(findings))
            self.assertNotIn("listing-collapse-risk", _rules(findings))


class RuntimeConstructTests(unittest.TestCase):
    def test_unguarded_subagent_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Spawn a subagent to do the work.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("subagent-dependency", _rules(findings))
            f = next(f for f in findings if f["rule"] == "subagent-dependency")
            self.assertEqual(f["targets"], ["claude-ai"])

    def test_guarded_subagent_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Research via subagents if available, otherwise inline.\n")
            findings, _ = lint_portability(skill)
            self.assertNotIn("subagent-dependency", _rules(findings))

    def test_claude_cli_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Run `claude -p` to optimize.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("claude-cli-dependency", _rules(findings))

    def test_browser_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "scripts").mkdir()
            (skill / "scripts" / "viewer.py").write_text("import http.server\n")
            findings, _ = lint_portability(skill)
            self.assertIn("browser-display-dependency", _rules(findings))


class ThirdPartyImportTests(unittest.TestCase):
    def _skill_with_script(self, td, script_src):
        skill = _skill(Path(td), "name: x\ndescription: d")
        (skill / "scripts").mkdir()
        (skill / "scripts" / "tool.py").write_text(script_src)
        return skill

    def test_thirdparty_import_flagged_for_cowork(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._skill_with_script(td, "import yaml\n")
            findings = check_thirdparty_imports(skill)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["rule"], "thirdparty-import")
            self.assertEqual(findings[0]["targets"], ["cowork"])
            self.assertIn("yaml", findings[0]["message"])

    def test_stdlib_import_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._skill_with_script(td, "import os, sys, json\nfrom pathlib import Path\n")
            self.assertEqual(check_thirdparty_imports(skill), [])

    def test_relative_import_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._skill_with_script(td, "from . import utils\nfrom .utils import x\n")
            self.assertEqual(check_thirdparty_imports(skill), [])

    def test_sibling_module_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "scripts").mkdir()
            (skill / "scripts" / "utils.py").write_text("X = 1\n")
            (skill / "scripts" / "tool.py").write_text("from utils import X\nimport utils\n")
            self.assertEqual(check_thirdparty_imports(skill), [])


class TargetFilterAndStructureTests(unittest.TestCase):
    def test_filter_by_target(self):
        findings = [
            {"rule": "a", "targets": ["cowork"]},
            {"rule": "b", "targets": ["claude-ai"]},
            {"rule": "c", "targets": ["claude-ai", "cowork"]},
        ]
        self.assertEqual(_rules(_filter_by_target(findings, "cowork")), {"a", "c"})
        self.assertEqual(_rules(_filter_by_target(findings, "claude-ai")), {"b", "c"})
        self.assertEqual(len(_filter_by_target(findings, "all")), 3)

    def test_missing_skill_md_returns_structural_error(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "empty"
            d.mkdir()
            findings, err = lint_portability(d)
            self.assertEqual(findings, [])
            self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
