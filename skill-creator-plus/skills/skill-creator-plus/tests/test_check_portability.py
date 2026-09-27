import math
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
    check_combined_compaction_budget,
    check_plugin_bin_directory,
    find_plugin_root,
    attached_token_cost,
    COMBINED_TOKEN_CAP,
    COMPACTION_TOKEN_CAP,
    check_outputs_prefix,
    _filter_by_target,
    COMPACTION_CAP_CHARS,
    COMPACTION_MARKER_CHARS,
    COMPACTION_TRIGGER_CHARS,
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

    def test_boundary_is_the_trigger_not_the_survivor(self):
        """The two constants are 102 chars apart and the gate must use the trigger.

        The runtime leaves content alone while `Math.round(len/4) <= 5000`, and JS `Math.round`
        is half-up, so 20,001 chars round to 5000 (untouched) and 20,002 round to 5001
        (truncated). Gating on COMPACTION_CAP_CHARS instead flags the whole 19,901..20,001 band
        for a truncation that never happens.
        """
        # what survives is 19,900 -- but nothing at that length is ever touched
        self.assertEqual(check_compaction_budget("a" * COMPACTION_CAP_CHARS), [])
        for n in (COMPACTION_CAP_CHARS + 1, 20000, COMPACTION_TRIGGER_CHARS - 1):
            self.assertEqual(check_compaction_budget("a" * n), [],
                             f"{n} chars is below the trigger; the runtime never truncates it")
        self.assertEqual(len(check_compaction_budget("a" * COMPACTION_TRIGGER_CHARS)), 1)

    def test_trigger_matches_the_runtime_round_half_up(self):
        """Re-derive the trigger from the runtime's own gate rather than trusting the literal.

        Runtime: `if ($c(e) <= t) return e` with `$c = Math.round(len/4)` and `t = 5000`.
        Python's round() is banker's rounding, so half-up is spelled out explicitly.
        """
        def truncates(n):
            return math.floor(n / 4 + 0.5) > 5000          # JS Math.round is half-up
        self.assertFalse(truncates(COMPACTION_TRIGGER_CHARS - 1))
        self.assertTrue(truncates(COMPACTION_TRIGGER_CHARS))
        self.assertEqual(min(n for n in range(19000, 21000) if truncates(n)),
                         COMPACTION_TRIGGER_CHARS)
        # and what survives is the marker's complement, not the trigger
        self.assertEqual(5000 * 4 - COMPACTION_MARKER_CHARS, COMPACTION_CAP_CHARS)


def _plugin(tmp: Path, skill_sizes) -> Path:
    """Build a plugin dir with one skill per entry in `skill_sizes` (name -> SKILL.md char count).

    Returns the FIRST skill's path -- the rule is reached by linting a member skill, not the
    plugin, because that is how the CLI is actually invoked.
    """
    root = tmp / "plug"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "plug"}')
    first = None
    for name, n in skill_sizes.items():
        d = root / "skills" / name
        d.mkdir(parents=True)
        head = f"---\nname: {name}\ndescription: d\n---\n\n"
        (d / "SKILL.md").write_text(head + "a" * max(0, n - len(head)))
        first = first or d
    return first


class CombinedCompactionCapTests(unittest.TestCase):
    """The combined cap zeroes a skill silently -- author time is the only place it is detectable."""

    def test_cost_is_post_truncation_so_a_huge_skill_is_capped(self):
        # the runtime sums $c(M) where M is already truncated: CAP chars + a 100-char marker
        # == TOKEN_CAP*4 chars exactly, so an over-cap skill costs the cap and never more.
        self.assertEqual(attached_token_cost(500_000), COMPACTION_TOKEN_CAP)
        self.assertEqual(attached_token_cost(COMPACTION_TRIGGER_CHARS), COMPACTION_TOKEN_CAP)
        # just under the trigger it is NOT truncated, so it costs its own rounded length --
        # which is the one input where the cost briefly dips below the cap
        self.assertEqual(attached_token_cost(COMPACTION_TRIGGER_CHARS - 1), 5000)
        self.assertEqual(attached_token_cost(4000), 1000)
        self.assertEqual(attached_token_cost(0), 0)

    def test_half_up_rounding_not_bankers(self):
        # Python's round(0.5) == 0; JS Math.round(0.5) == 1. Only the latter matches the runtime.
        self.assertEqual(attached_token_cost(2), 1)
        self.assertEqual(attached_token_cost(6), 2)

    def test_standalone_skill_is_never_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d", body="a" * 60_000)
            self.assertEqual(check_combined_compaction_budget(skill), [])

    def test_single_skill_plugin_is_never_flagged(self):
        # one skill cannot blow a 25,000-token budget: it is capped at 5,000
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {"only": 400_000})
            self.assertEqual(check_combined_compaction_budget(skill), [])

    def test_five_over_cap_skills_fit_and_six_do_not(self):
        """The exact boundary: 5 x 5,000 == 25,000 fits; the sixth is what gets zeroed."""
        big = 40_000
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {f"s{i}": big for i in range(5)})
            self.assertEqual(check_combined_compaction_budget(skill), [],
                             "25,000 is the cap, not one under it -- the runtime uses `>`")
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {f"s{i}": big for i in range(6)})
            findings = check_combined_compaction_budget(skill)
            self.assertEqual(len(findings), 1)
            f = findings[0]
            self.assertEqual(f["rule"], "compaction-zeroing-risk")
            self.assertEqual(f["severity"], "advisory")
            self.assertEqual(f["targets"], ["claude-code", "cowork"])
            self.assertEqual(f["location"], ".claude-plugin/plugin.json")

    def test_message_names_the_silent_failure_not_just_the_size(self):
        """A size number alone would send an author to the wrong fix. The message must say that
        the skill is dropped whole, leaves no marker, and is evicted least-recently-invoked-first.
        """
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {f"s{i}": 40_000 for i in range(6)})
            msg = check_combined_compaction_budget(skill)[0]["message"]
            for phrase in ("dropped WHOLE", "no marker", "least-recently-invoked",
                           "Lower bound", "references/"):
                self.assertIn(phrase, msg)

    def test_many_small_skills_also_trip_it(self):
        """Not just a big-skill problem: 26 skills of 4,000 chars are each well under the
        per-skill cap and still blow the combined one."""
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {f"s{i}": 4_000 for i in range(26)})
            self.assertEqual(len(check_combined_compaction_budget(skill)), 1)

    def test_reached_through_the_normal_lint_entry_point(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {f"s{i}": 40_000 for i in range(6)})
            findings, err = lint_portability(skill)
            self.assertIsNone(err)
            self.assertIn("compaction-zeroing-risk", _rules(findings))


class PluginBinDirectoryTests(unittest.TestCase):
    """A top-level bin/ is fatal to org distribution and invisible to every local gate.

    `claude plugin validate` passes a plugin carrying one (measured, 2.1.252 -- only an unrelated
    `author` warning), and the admin-side UI error is generic ("Marketplace sync failed. Check the
    repository URL and try again"), with the real message only in the renderer log. So the finding
    has to come from here or from nowhere.
    """

    @staticmethod
    def _with_bin(tmp: Path, entries=("tool",), where="root"):
        skill = _plugin(tmp, {"only": 500})
        root = skill.parent.parent                 # skills/only -> skills -> plugin root
        base = {"root": root,
                "skill": skill,
                "above": root.parent}[where]
        (base / "bin").mkdir(parents=True, exist_ok=True)
        for e in entries:
            (base / "bin" / e).write_text("#!/bin/sh\nexit 0\n")
        return skill

    def test_top_level_bin_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._with_bin(Path(td))
            findings = check_plugin_bin_directory(skill)
            self.assertEqual(len(findings), 1)
            f = findings[0]
            self.assertEqual(f["rule"], "plugin-bin-directory")
            self.assertEqual(f["severity"], "warning")
            self.assertEqual(f["targets"], ["claude-ai"], "the rule is lane-specific, not global")
            self.assertEqual(f["location"], "bin/")
            self.assertIn("bin/tool", f["message"])

    def test_message_carries_what_no_local_gate_says(self):
        """A bare 'you have a bin/' would read as style advice. It must say the plugin is
        rejected, that `plugin validate` will not warn, that CLI-only plugins are fine, and
        where to go instead -- including that the documented substitute needs a hook/mcpServers
        config and is empty in a shell."""
        with tempfile.TemporaryDirectory() as td:
            msg = check_plugin_bin_directory(self._with_bin(Path(td)))[0]["message"]
            for phrase in ("UNDISTRIBUTABLE", "organization settings",
                           "Plugin contains a top-level bin/ directory",
                           "does not warn", "lane-specific, not a deprecation",
                           "GitHub and local-CLI installs are unaffected",
                           "scripts/", "mcpServers", "empty string",
                           "assets/skill-script-invocation.md"):
                self.assertIn(phrase, msg)

    def test_entry_list_is_truncated_with_a_count(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._with_bin(Path(td), entries=("a", "b", "c", "d", "e"))
            msg = check_plugin_bin_directory(skill)[0]["message"]
            self.assertIn("bin/a, bin/b, bin/c (+2 more)", msg)

    def test_standalone_skill_is_never_flagged(self):
        """No plugin.json anywhere above means nothing is being distributed as a plugin."""
        with tempfile.TemporaryDirectory() as td:
            skill = _skill(Path(td), "name: x\ndescription: d")
            (skill / "bin").mkdir()
            (skill / "bin" / "tool").write_text("x")
            self.assertEqual(check_plugin_bin_directory(skill), [])

    def test_plugin_without_bin_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(check_plugin_bin_directory(_plugin(Path(td), {"only": 500})), [])

    def test_empty_bin_dir_does_not_fire(self):
        """git cannot commit an empty directory, so an empty bin/ never reaches intake."""
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {"only": 500})
            (skill.parent.parent / "bin").mkdir()
            self.assertEqual(check_plugin_bin_directory(skill), [])

    def test_bin_inside_the_skill_is_not_the_plugin_root(self):
        """Only the directory beside .claude-plugin/plugin.json is what intake reads."""
        with tempfile.TemporaryDirectory() as td:
            skill = self._with_bin(Path(td), where="skill")
            self.assertEqual(check_plugin_bin_directory(skill), [])

    def test_bin_above_the_plugin_is_not_the_plugin_root(self):
        """A marketplace repo has two candidate roots; a bin/ at the OUTER one is an ordinary
        project CLI, correctly placed, and must not be flagged."""
        with tempfile.TemporaryDirectory() as td:
            skill = self._with_bin(Path(td), where="above")
            self.assertEqual(check_plugin_bin_directory(skill), [])

    def test_nearest_manifest_wins(self):
        with tempfile.TemporaryDirectory() as td:
            skill = _plugin(Path(td), {"only": 500})
            root = skill.parent.parent
            self.assertEqual(find_plugin_root(skill), root.resolve())

    def test_reached_through_the_normal_lint_entry_point(self):
        with tempfile.TemporaryDirectory() as td:
            skill = self._with_bin(Path(td))
            findings, err = lint_portability(skill)
            self.assertIsNone(err)
            self.assertIn("plugin-bin-directory", _rules(findings))

    def test_only_reported_for_the_claude_ai_target(self):
        """Filtering matters here: the same tree is correct on the CLI lane and broken on the
        hosted one, so a claude-code run must stay silent about it."""
        with tempfile.TemporaryDirectory() as td:
            findings, _ = lint_portability(self._with_bin(Path(td)))
            self.assertIn("plugin-bin-directory", _rules(_filter_by_target(findings, "claude-ai")))
            self.assertNotIn("plugin-bin-directory",
                             _rules(_filter_by_target(findings, "claude-code")))
            self.assertNotIn("plugin-bin-directory",
                             _rules(_filter_by_target(findings, "cowork")))


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
        the line goes verbatim to a sub-agent, and a relative path never reaches the eval run
        directory in Cowork: on older local Desktop the file-tool cwd was the outputs directory, so
        it doubled to `outputs/outputs/...`; on Desktop 2.7032.0+ the file tools refuse it. The
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

    def test_bare_workspace_name_is_not_this_rules_concern(self):
        # A bare workspace name is a different (lane-dependent) question -- correct in the CLI,
        # refused by Cowork's file tools from Desktop 2.7032.0. This rule only owns `outputs/`.
        self.assertEqual(self._fires("Name it `<skill-name>-workspace/`.\n"), [])

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
            ("**file tools** need the absolute outputs path",
             "the file-tool path form is lost, and a bare path is what gets refused"),
            ("Your **shell** may spell that directory differently",
             "the shell-vs-file-tool split is lost"),
            ("give sub-agents both, labelled", "sub-agents get one form and misuse it"),
            # The one-pass route's verification doctrine. Both sentences were ported INLINE rather
            # than cross-referenced, because the eval-section text they came from sits past the cut
            # -- a pointer into it would dangle in exactly the compacted session this guards.
            ("whether the script or the *test* is wrong",
             "the one-pass route loses its 'the fixture can be wrong' epistemics"),
            ("belongs in the skill's own `scripts/`",
             "the one-pass route loses the bundle-the-check guidance"),
            # The size rule must state the metric that actually binds. A line count cannot protect
            # a character budget -- this very file passes "under 500 lines" at 2.07x the cap.
            ("under 19,900 characters — measure with `wc -m`",
             "the size rule reverts to a line count, which cannot enforce the real limit"),
            # Truncation recovery is only useful if it survives the truncation it describes.
            ("re-read `SKILL.md` from disk",
             "the truncation-recovery instruction is itself truncated away"),
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
