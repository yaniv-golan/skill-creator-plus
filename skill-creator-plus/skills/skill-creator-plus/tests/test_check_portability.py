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
    check_compaction_budget,
    check_outputs_prefix,
    _filter_by_target,
    COMPACTION_CAP_CHARS,
    DESC_HARD_CAP,
    TARGETS,
)

TARGETS_SORTED = sorted(TARGETS)


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
            self.assertNotIn("listing-desc-drop-risk", _rules(findings))
            self.assertNotIn("listing-collapse-risk", _rules(findings))

    def test_large_description_flags_drop_risk_not_collapse(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), f"name: x\ndescription: {'a' * 900}")
            findings, _ = lint_portability(skill)
            self.assertIn("listing-desc-drop-risk", _rules(findings))
            f = next(f for f in findings if f["rule"] == "listing-desc-drop-risk")
            self.assertEqual(f["severity"], "advisory")
            # The corrected model: THIS description gets dropped when unused — not every skill at once.
            self.assertNotIn("every skill", f["message"])
            self.assertIn("least-recently-used", f["message"])


class CompactionBudgetTests(unittest.TestCase):
    """The cap is a hardcoded character count in the runtime, so this check is exact."""

    def test_under_cap_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d", body="short body\n")
            findings, _ = lint_portability(skill)
            self.assertNotIn("compaction-truncation-risk", _rules(findings))

    def test_over_cap_flags_advisory_with_the_cut_line(self):
        with tempfile.TemporaryDirectory() as td:
            body = "".join(f"line {i} padding padding padding padding\n" for i in range(700))
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            self.assertGreater(len((skill / "SKILL.md").read_text()), COMPACTION_CAP_CHARS)
            findings, _ = lint_portability(skill)
            self.assertIn("compaction-truncation-risk", _rules(findings))
            f = next(f for f in findings if f["rule"] == "compaction-truncation-risk")
            self.assertEqual(f["severity"], "advisory")
            self.assertEqual(f["targets"], ["claude-code", "cowork"])
            # names the character unit, not tokens — the whole point of the rule
            self.assertIn("wc -m", f["message"])
            self.assertIn("roughly line", f["message"])

    def test_boundary_exactly_at_cap_is_clean(self):
        text = "a" * COMPACTION_CAP_CHARS
        self.assertEqual(check_compaction_budget(text), [])
        self.assertEqual(len(check_compaction_budget(text + "a")), 1)


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

    def test_absent_thirdparty_import_flagged_as_advisory(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._skill_with_script(td, "import humanize\n")
            findings = check_thirdparty_imports(skill)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["rule"], "thirdparty-import")
            self.assertEqual(findings[0]["targets"], ["cowork"])
            self.assertEqual(findings[0]["severity"], "advisory")
            self.assertIn("humanize", findings[0]["message"])

    def test_cowork_preinstalled_imports_not_flagged(self):
        """The image ships the data/document stack a generated skill is most likely to import."""
        with tempfile.TemporaryDirectory() as td:
            skill = self._skill_with_script(
                td,
                "import pandas as pd\nimport numpy as np\nimport yaml\nimport requests\n"
                "from bs4 import BeautifulSoup\nfrom PIL import Image\nimport openpyxl\n"
                "import matplotlib.pyplot as plt\nimport docx\nimport pptx\n",
            )
            self.assertEqual(check_thirdparty_imports(skill), [])

    def test_preinstalled_and_absent_mixed_flags_only_the_absent(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._skill_with_script(td, "import pandas\nimport humanize\n")
            findings = check_thirdparty_imports(skill)
            self.assertEqual(len(findings), 1)
            self.assertIn("humanize", findings[0]["message"])
            # Anchored at the humanize line (2), not the pandas line (1).
            self.assertTrue(findings[0]["location"].endswith(":2"), findings[0]["location"])

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
    """Covers the two rules that replaced `file-delivery-tool-hardcoded`.

    The old rule warned on naming EITHER tool at all — that premise was invalidated by
    binary-verified Cowork baselines: on remote cloud-container Cowork, writing a file and
    stating the path delivers nothing (the filesystem is discarded and nothing watches the
    outputs directory), so the tool call IS the delivery, and naming BOTH tools capability-
    conditionally is the correct, target-state pattern. `delivery-tool-single-lane` inverts the
    old rule's premise: naming both is clean; naming only one strands the lane served by the
    other. `delivery-conditional-deliverable` narrowly targets the real upstream bug (gating the
    artifact's own packaging on tool availability), not conditionality in general.
    """

    def test_present_files_only_flags_single_lane(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Use the present_files tool to show the report.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("delivery-tool-single-lane", _rules(findings))
            f = next(f for f in findings if f["rule"] == "delivery-tool-single-lane")
            self.assertEqual(f["severity"], "warning")
            self.assertEqual(f["targets"], list(TARGETS_SORTED))
            self.assertIn("present_files", f["message"])
            self.assertIn("SendUserFile", f["message"])
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_mcp_prefixed_present_files_only_flags_single_lane(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Call mcp__cowork__present_files with the path.\n")
            findings, _ = lint_portability(skill)
            self.assertIn("delivery-tool-single-lane", _rules(findings))

    def test_senduserfile_only_flags_single_lane(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Deliver it with SendUserFile.\n")
            findings, _ = lint_portability(skill)
            f = next(f for f in findings if f["rule"] == "delivery-tool-single-lane")
            self.assertEqual(f["targets"], list(TARGETS_SORTED))
            self.assertIn("SendUserFile", f["message"])
            self.assertIn("present_files", f["message"])

    def test_naming_both_suppresses_single_lane(self):
        """Key inversion vs the old rule: naming both tools is the correct pattern, not a bug."""
        with tempfile.TemporaryDirectory() as td:
            body = "Use present_files here.\nElsewhere use SendUserFile.\n"
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_both_tools_named_across_separate_files_suppresses_single_lane(self):
        """Determination is skill-wide, not per file.

        A skill that documents `present_files` in one reference doc and `SendUserFile` in
        another is a legitimate structure — it names both lanes, just not on the same line or
        in the same file. Per-file scoping would false-positive here (one finding per file,
        each seeing only one tool); skill-wide scoping correctly sees both and stays silent.
        """
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="Use present_files to show the report.\n")
            (skill / "references").mkdir()
            (skill / "references" / "remote.md").write_text(
                "On the remote lane, use SendUserFile instead.\n")
            findings, _ = lint_portability(skill)
            self.assertEqual(
                [f for f in findings if f["rule"] == "delivery-tool-single-lane"], [],
                "naming both tools across two separate files must not trip single-lane",
            )

    def test_correct_capability_conditional_sentence_is_completely_clean(self):
        """D1': the target-state pattern from the docs task — must trip neither new rule."""
        with tempfile.TemporaryDirectory() as td:
            body = (
                "If a tool for surfacing files to the user is available (`present_files`, or "
                "`SendUserFile` on remote surfaces), present the final file(s) with it; if "
                "neither exists, state the path.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_upstream_bug_pattern_flags_conditional_deliverable(self):
        """The real bug (anthropics/claude-code#36438): packaging itself gated on the tool."""
        with tempfile.TemporaryDirectory() as td:
            body = (
                "### Package and Present (only if `present_files` tool is available)\n"
                "Check whether you have access to the `present_files` tool. If you don't, "
                "skip this step.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertIn("delivery-conditional-deliverable", _rules(findings))
            f = next(f for f in findings if f["rule"] == "delivery-conditional-deliverable")
            self.assertEqual(f["severity"], "warning")
            self.assertEqual(f["targets"], list(TARGETS_SORTED))

    def test_named_tools_only_if_available_with_fallback_stays_clean(self):
        """Merge-gate review table row 1: naming both tools + 'only if' + a stated fallback.

        No production verb (package/write/save/...) governs the skip/omit clause — it's the
        *presentation* call that's conditional, not producing the file — and the sentence states
        a fallback ("otherwise state the path") besides. Must NOT fire.
        """
        with tempfile.TemporaryDirectory() as td:
            body = (
                "Present it with present_files or SendUserFile only if such a tool is "
                "available; otherwise state the path.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_deployed_skill_creator_wording_stays_clean(self):
        """Merge-gate review table row 2: real, deployed skill-creator wording.

        "...present_files, or SendUserFile in Cowork remote. If you have neither, skip this
        step." — the skip/omit phrase ("skip this step") governs *presenting* the file, not
        producing it; no production verb appears in that clause. Must NOT fire.
        """
        with tempfile.TemporaryDirectory() as td:
            body = (
                "On Cowork, present the file with `present_files`, or `SendUserFile` in Cowork "
                "remote. If you have neither, skip this step.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_wrapped_upstream_bug_still_flagged_regardless_of_line_breaks(self):
        """Clause-scoping (not line-scoping) means re-wrapping the upstream bug text across
        different physical lines must not change the verdict."""
        with tempfile.TemporaryDirectory() as td:
            body = (
                "Package the deliverable and present it, but only if the\n"
                "`present_files` tool is available in this session. If it isn't,\n"
                "skip this step entirely and do nothing.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertIn("delivery-conditional-deliverable", _rules(findings))

    def test_marker_suppresses_both_rules_in_md(self):
        with tempfile.TemporaryDirectory() as td:
            body = ("<!-- portability-allow: file-delivery-tool -->\n"
                    "Only if `present_files` is available should you package and present it; "
                    "if you don't have it, skip this step.\n")
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_marker_suppresses_both_rules_in_script(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "scripts").mkdir()
            (skill / "scripts" / "deliver.py").write_text(
                "# portability-allow: file-delivery-tool\n"
                "TOOL = 'present_files'  # only if available, otherwise skip it\n")
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_unmarked_script_is_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "scripts").mkdir()
            (skill / "scripts" / "deliver.py").write_text('TOOL = "present_files"\n')
            findings, _ = lint_portability(skill)
            self.assertIn("delivery-tool-single-lane", _rules(findings))

    def test_near_miss_names_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            body = "We represent_files and use present_filesystem and present_files_v2.\n"
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))

    def test_clean_capability_language_without_naming_either_tool_not_flagged(self):
        """Naming zero tools is not naming exactly one — must not trip single-lane."""
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d",
                           body="If a file-delivery tool is available, surface the file.\n")
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))
            self.assertNotIn("delivery-conditional-deliverable", _rules(findings))


class DeliveryAllowMarkerContextTests(unittest.TestCase):
    """Covers the fix for the marker's self-exemption bug: `_DELIVERY_ALLOW_RE` used to match the
    marker phrase anywhere in a file's text, including inside prose merely *describing* it (e.g. a
    doc explaining the escape hatch) — which silently disabled both delivery rules for that file
    without an actual marker being present. The marker must now appear in comment context (a
    leading `#` comment line, or an HTML `<!-- -->` comment).
    """

    def test_prose_mention_of_marker_does_not_suppress(self):
        with tempfile.TemporaryDirectory() as td:
            body = (
                "A file that genuinely must deviate from this pattern suppresses either rule "
                "with a file-scoped `portability-allow: file-delivery-tool` comment.\n"
                "Use present_files to show the report.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertIn(
                "delivery-tool-single-lane", _rules(findings),
                "prose merely describing the marker must not suppress the rule it describes",
            )

    def test_hash_comment_marker_suppresses(self):
        with tempfile.TemporaryDirectory() as td:
            body = (
                "# portability-allow: file-delivery-tool\n"
                "Use present_files to show the report.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))

    def test_html_comment_marker_suppresses(self):
        with tempfile.TemporaryDirectory() as td:
            body = (
                "<!-- portability-allow: file-delivery-tool -->\n"
                "Use present_files to show the report.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertNotIn("delivery-tool-single-lane", _rules(findings))

    def test_marker_mentioned_mid_sentence_without_comment_syntax_does_not_suppress(self):
        with tempfile.TemporaryDirectory() as td:
            body = (
                "See the portability-allow: file-delivery-tool marker for the escape hatch.\n"
                "Use present_files to show the report.\n"
            )
            skill = _skill(Path(td), "name: x\ndescription: d", body=body)
            findings, _ = lint_portability(skill)
            self.assertIn("delivery-tool-single-lane", _rules(findings))


class OutputsPrefixTests(unittest.TestCase):
    """The 13 cases the rule was prototyped against, plus scoping and suppression.

    Cases 5-8 and 13 are regression pins for real in-repo text that an earlier, wider
    formulation of this rule fired on. Case 10 is the sharpest: the sentence that TELLS an
    author not to do this contains the string `outputs/`, and a rule that flags its own fix
    is the failure mode `delivery-tool-single-lane` was written to replace.
    """

    def _fires(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            d = _skill(Path(tmp), "name: s\ndescription: d", body)
            return [f["rule"] for f in check_outputs_prefix(d)]

    def test_plain_workspace_path_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("Create the workspace at `outputs/my-skill-workspace/`.\n"))

    def test_dot_slash_form_fires(self):
        # ./outputs/... normalises and doubles identically in production.
        self.assertIn("outputs-prefix-relative", self._fires("Create it at `./outputs/my-skill-workspace/`.\n"))

    def test_templated_placeholder_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("Put results in `outputs/<skill-name>-workspace/`.\n"))

    def test_markdown_bold_emphasis_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("Write to **outputs/my-skill-workspace/**\n"))

    def test_workspace_without_hyphen_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("Put results in outputs/workspace/\n"))

    def test_underscore_separator_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("Use `outputs/eval_workspace/`\n"))

    def test_key_equals_value_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("path=outputs/x-workspace\n"))

    def test_plural_workspaces_is_clean(self):
        self.assertEqual(self._fires("See outputs/workspaces/ for many\n"), [])

    def test_unquoted_midsentence_fires(self):
        self.assertIn("outputs-prefix-relative", self._fires("Put the workspace under outputs/csv-to-md-workspace and go.\n"))

    def test_eval_dispatch_relative_outputs_is_a_known_MISS_not_a_pass(self):
        """This rule does NOT catch `outputs/user_notes.md` in a dispatch prompt -- and that line
        was a REAL BUG, not correct text.

        An earlier version of this suite asserted it "is_clean", which certified a live defect:
        the line goes verbatim to a sub-agent whose file-tool cwd IS the outputs directory, so
        the path doubles to `outputs/outputs/...` and lands outside the eval run directory. The
        shipped SKILL.md now uses an explicit absolute placeholder instead.

        The miss is recorded rather than fixed. Covering the general class needs a predicate that
        knows what base a bare `outputs/` is relative to; a regex measured against 263 installed
        skills flagged the canonical CORRECT explanations of this very bug at ~1-in-18 precision.
        That is the `file-delivery-tool-hardcoded` failure mode (see check_portability.py), so the
        class stays prose guidance in references/environments.md, not a rule.
        """
        self.assertEqual(self._fires("- Also write outputs/user_notes.md: notes\n"), [],
                         "known miss -- if this ever fires, a predicate was found; update the docs")

    def test_with_skill_outputs_is_clean(self):
        self.assertEqual(self._fires("- Save outputs to: <workspace>/iteration-<N>/with_skill/outputs/\n"), [])

    def test_run_dir_outputs_is_clean(self):
        self.assertEqual(self._fires("Located at `<run-dir>/outputs/metrics.json`.\n"), [])

    def test_non_workspace_relative_outputs_is_clean(self):
        self.assertEqual(self._fires("The grader writes to `outputs/grading.json` in each run dir.\n"), [])

    def test_report_under_build_workspace_is_clean(self):
        self.assertEqual(self._fires("Save the report to outputs/report.html under the build workspace.\n"), [])

    def test_the_rules_own_fix_text_is_clean(self):
        self.assertEqual(self._fires("Never prefix it with `outputs/`: that nests a second outputs level.\n"), [])

    def test_absolute_mnt_outputs_is_clean(self):
        self.assertEqual(self._fires("Under the shell it is `/sessions/<id>/mnt/outputs/my-skill-workspace/`.\n"), [])

    def test_the_correct_answer_is_clean(self):
        self.assertEqual(self._fires("Use a bare relative path -- `<skill-name>-workspace/`.\n"), [])

    def test_workspace_placeholder_subdir_is_clean(self):
        self.assertEqual(self._fires("Snapshot to `<workspace>/skill-snapshot/`.\n"), [])

    def test_html_comment_marker_suppresses(self):
        body = "<!-- portability-allow: outputs-prefix -->\nCreate it at `outputs/my-skill-workspace/`.\n"
        self.assertEqual(self._fires(body), [])

    def test_fenced_code_example_of_the_marker_does_not_suppress(self):
        """Documenting the escape hatch must not disable it -- the most natural spoof."""
        body = ("Example:\n```\n# portability-allow: outputs-prefix\n```\n"
                "Create it at `outputs/my-skill-workspace/`.\n")
        self.assertIn("outputs-prefix-relative", self._fires(body))

    def test_markdown_heading_form_does_not_suppress(self):
        """A leading `#` is a HEADING in markdown, not a comment -- it must not blind the file."""
        body = "# portability-allow: outputs-prefix\nCreate it at `outputs/my-skill-workspace/`.\n"
        self.assertIn("outputs-prefix-relative", self._fires(body))

    def test_targets_cowork_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _skill(Path(tmp), "name: s\ndescription: d", "Use `outputs/my-skill-workspace/`.\n")
            findings, _ = lint_portability(d)
            self.assertNotIn("outputs-prefix-relative", _rules(_filter_by_target(findings, "claude-code")))
            self.assertIn("outputs-prefix-relative", _rules(_filter_by_target(findings, "cowork")))

    def test_prose_mention_of_marker_does_not_suppress(self):
        """The marker only counts in comment context -- prose ABOUT it must not disable the rule.

        Mirrors DeliveryAllowMarkerContextTests: a reference doc explaining "suppress this with a
        `portability-allow: outputs-prefix` comment" must still be scanned, or documenting the
        escape hatch silently disables the rule for the file that documents it.
        """
        body = ("You can suppress this with a portability-allow: outputs-prefix comment.\n"
                "Create it at `outputs/my-skill-workspace/`.\n")
        self.assertIn("outputs-prefix-relative", self._fires(body))


class StrictGatingTests(unittest.TestCase):
    """`--strict` gates warnings and errors; advisories are informational by design."""

    def _run(self, skill, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, "-m", "scripts.check_portability", str(skill), *args],
            cwd=str(SCRIPT_DIR.parent), capture_output=True, text=True,
        )

    def test_advisory_alone_does_not_gate_under_strict(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), f"name: x\ndescription: {'a' * 900}")
            r = self._run(skill, "--target", "claude-code", "--strict")
            self.assertIn("listing-desc-drop-risk", r.stdout)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_advisory_gates_with_strict_advisories(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), f"name: x\ndescription: {'a' * 900}")
            r = self._run(skill, "--target", "claude-code", "--strict", "--strict-advisories")
            self.assertEqual(r.returncode, 1, r.stdout)

    def test_error_gates_without_strict(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), f"name: x\ndescription: {'a' * (DESC_HARD_CAP + 10)}")
            r = self._run(skill)
            self.assertEqual(r.returncode, 1, r.stdout)


class SelfLintTests(unittest.TestCase):
    def test_this_skill_does_not_trip_outputs_prefix(self):
        """Pin against the REAL tree, not an excerpt -- an isolated-lines test would false-green.

        The earlier, wider formulation of this rule fired on SKILL.md's own eval dispatch block;
        testing those lines in isolation passed while the shipped file was flagged.
        """
        skill_root = Path(__file__).resolve().parent.parent
        self.assertEqual(check_outputs_prefix(skill_root), [])
        # Anti-gaming: clean must mean "no violation", not "rule switched off". Mirrors the
        # assertion the delivery self-lint carries.
        # Assert the SUPPRESSING FORM is absent, not the phrase: environments.md documents the
        # escape hatch in prose, which is correct and must not fail this.
        for name in ("SKILL.md", "references/environments.md"):
            self.assertNotIn("<!-- portability-allow: outputs-prefix",
                             (skill_root / name).read_text(),
                             f"{name} suppresses the rule instead of complying with it")

    def test_load_bearing_workspace_facts_survive_compaction(self):
        """The instructions an agent needs AT the workspace step must be in the surviving prefix.

        Not a delta gate: `SKILL.md` may legitimately grow. What must stay true is that the three
        facts an agent acts on when it creates the workspace are still readable after a session
        auto-compacts, because compaction truncates to COMPACTION_CAP_CHARS and writes the
        truncation back. This nearly regressed twice while it was being written -- once from a
        routine version bump (frontmatter sits ahead of this text) and once from adding an
        explanatory clause earlier in the file -- so it is pinned rather than trusted.

        If this fails, do NOT move the cap. Move content out of SKILL.md into references/, which
        is read on demand and never truncated.
        """
        skill_md = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text()
        surviving = skill_md[:COMPACTION_CAP_CHARS]
        for fact, why in [
            ("<abs-workspace>", "the shell/sub-agent path placeholder is never defined"),
            ("**file tools** already sit", "the cwd claim reads as unqualified, which is the bug"),
            ("Your **shell** does not", "the shell-vs-file-tool split is lost"),
        ]:
            self.assertIn(fact, surviving,
                          f"dropped past the compaction cut: {why}. Move content to references/.")

    def test_shipped_baseline_rule_ids_are_exactly_these(self):
        """`docs/DEVELOPMENT.md` says a NEW rule id is the regression signal -- enforce that.

        The docs state a baseline of 4 findings and that the suite (not the CLI, which CI does not
        run) is what guards it. Nothing asserted the SET, so a new rule firing on our own tree
        would have gone unnoticed. Adding a rule that legitimately fires here means updating this
        list deliberately, which is the point.
        """
        skill_root = Path(__file__).resolve().parent.parent
        findings, structural_error = lint_portability(skill_root)
        self.assertIsNone(structural_error)
        self.assertEqual(
            _rules(findings),
            {"compaction-truncation-risk", "subagent-dependency",
             "claude-cli-dependency", "browser-display-dependency"},
            "the shipped skill's finding set changed -- a NEW rule id here is a regression signal, "
            "not a number to update without reading why it fired",
        )

    def test_this_skill_trips_neither_delivery_rule(self):
        """Pins the SKILL.md / environments.md wording against regression.

        `validate.yml` runs this suite, so a regression here is a red CI, not an advisory.

        SKILL.md teaches the corrected, lane-aware delivery guidance (see "Delivering Files the
        Skill Produces" and the packaging step) but names NEITHER `present_files` nor
        `SendUserFile` — it phrases delivery by outcome, not by tool name — so
        `delivery-tool-single-lane` correctly does not fire on it. Of the two files in this skill
        that do name either tool, `scripts/check_portability.py` carries the file-scoped
        `portability-allow: file-delivery-tool` marker (it scans its own source and its finding
        messages unavoidably pair tool names with skip/omit-adjacent phrasing); but
        `references/environments.md`, which documents the constraint, carries no marker at all —
        its prose never combines a tool name with a skip/omit phrase *and* a production verb in
        the same clause, so it stays clean on its own merits. (Prior to the marker-context fix,
        environments.md relied on a prose *mention* of the marker's name to blanket-suppress
        both rules — that was itself the bug fixed here; see `DeliveryAllowMarkerContextTests`.)
        """
        skill_root = Path(__file__).resolve().parent.parent
        skill_md = skill_root / "SKILL.md"
        self.assertTrue(skill_md.exists(), "skill root misresolved")
        findings, err = lint_portability(skill_root)
        self.assertIsNone(err)
        offenders = [f for f in findings
                     if f["rule"] in ("delivery-tool-single-lane", "delivery-conditional-deliverable")]
        self.assertEqual(offenders, [], f"skill-creator-plus trips a delivery rule: {offenders}")
        # A zero-findings result could be gamed by slapping the suppression marker on
        # SKILL.md instead of actually avoiding a single-lane tool mention — that would
        # silence both rules file-wide (including for a genuine future regression) while
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
