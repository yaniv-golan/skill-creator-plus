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


class FileDeliveryToolTests(unittest.TestCase):
    def test_present_files_flagged_for_all_three_targets(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Use the present_files tool to show the report.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("file-delivery-tool-hardcoded", _rules(findings))
            f = next(f for f in findings if f["rule"] == "file-delivery-tool-hardcoded")
            self.assertEqual(f["severity"], "warning")
            self.assertEqual(f["targets"], ["claude-ai", "claude-code", "cowork"])
            # Leading clause, not substring — every message names both tools in its explanation.
            self.assertTrue(f["message"].startswith(
                "names the file-delivery tool `present_files`"), f["message"][:80])

    def test_mcp_prefixed_present_files_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Call mcp__cowork__present_files with the path.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_senduserfile_excludes_claude_code_target(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Deliver it with SendUserFile.\n")
            findings, _ = lint_portability(skill)
            f = next(f for f in findings if f["rule"] == "file-delivery-tool-hardcoded")
            self.assertEqual(f["targets"], ["claude-ai", "cowork"])

    def test_both_names_emit_two_findings_with_own_targets(self):
        """D3: per-name findings — a merged finding would union targets wrongly."""
        with tempfile.TemporaryDirectory() as td:
            body = "Use present_files here.\nElsewhere use SendUserFile.\n"
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            hits = [f for f in findings if f["rule"] == "file-delivery-tool-hardcoded"]
            self.assertEqual(len(hits), 2)
            # Every message explains BOTH lanes by design, so only the leading clause is
            # tool-specific — do not discriminate on a substring anywhere in the message.
            # Emission order is fixed by _DELIVERY_TOOL_RES, so index is a stable key.
            self.assertTrue(hits[0]["message"].startswith(
                "names the file-delivery tool `present_files`"), hits[0]["message"][:80])
            self.assertEqual(hits[0]["targets"], ["claude-ai", "claude-code", "cowork"])
            self.assertTrue(hits[1]["message"].startswith(
                "names the file-delivery tool `SendUserFile`"), hits[1]["message"][:80])
            self.assertEqual(hits[1]["targets"], ["claude-ai", "cowork"])

    def test_if_available_does_not_suppress(self):
        """D5: guarding one name still strands the lane serving the other."""
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="If present_files is available, use it.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_lane_aware_prose_alone_does_not_suppress(self):
        """D5: natural per-lane prose is NOT a suppressor — only the marker is."""
        with tempfile.TemporaryDirectory() as td:
            body = ("The desktop-local sandbox is served present_files; remote "
                    "cloud-container Cowork gets SendUserFile.\n")
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_marker_suppresses_whole_md_file(self):
        with tempfile.TemporaryDirectory() as td:
            body = ("<!-- portability-allow: file-delivery-tool -->\n"
                    "Desktop-local Cowork serves present_files; remote serves SendUserFile.\n")
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_marker_suppresses_whole_script(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "scripts").mkdir()
            (skill / "scripts" / "deliver.py").write_text(
                "# portability-allow: file-delivery-tool\nTOOL = 'present_files'\n")
            findings, _ = lint_portability(skill)
            self.assertNotIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_unmarked_script_is_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "scripts").mkdir()
            (skill / "scripts" / "deliver.py").write_text('TOOL = "present_files"\n')
            findings, _ = lint_portability(skill)
            self.assertIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_clean_capability_language_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="If a file-delivery tool is available, surface the file.\n")
            findings, _ = lint_portability(skill)
            self.assertNotIn("file-delivery-tool-hardcoded", _rules(findings))

    def test_near_miss_names_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            body = "We represent_files and use present_filesystem and present_files_v2.\n"
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("file-delivery-tool-hardcoded", _rules(findings))


class SelfLintTests(unittest.TestCase):
    def test_this_skill_names_no_file_delivery_tool(self):
        """D6: pins the SKILL.md / environments.md wording against regression.

        `validate.yml` runs this suite, so a regression here is a red CI, not an advisory.
        """
        skill_root = Path(__file__).resolve().parent.parent
        skill_md = skill_root / "SKILL.md"
        self.assertTrue(skill_md.exists(), "skill root misresolved")
        findings, err = lint_portability(skill_root)
        self.assertIsNone(err)
        offenders = [f for f in findings if f["rule"] == "file-delivery-tool-hardcoded"]
        self.assertEqual(offenders, [], f"skill-creator-plus hardcodes a delivery tool: {offenders}")
        # A zero-findings result could be gamed by slapping the suppression marker on
        # SKILL.md instead of actually avoiding the hardcoded tool name — that would
        # silence the rule file-wide (including for a genuine future regression) while
        # still leaving SKILL.md having named a delivery tool. SKILL.md must name no
        # delivery tool at all, so it must never carry the marker.
        self.assertNotIn(
            "portability-allow: file-delivery-tool",
            skill_md.read_text(encoding="utf-8"),
            "SKILL.md must not carry the `portability-allow: file-delivery-tool` marker — "
            "SKILL.md is expected to name no file-delivery tool, so suppressing the rule "
            "there would hide a real regression instead of proving one doesn't exist.",
        )


if __name__ == "__main__":
    unittest.main()
