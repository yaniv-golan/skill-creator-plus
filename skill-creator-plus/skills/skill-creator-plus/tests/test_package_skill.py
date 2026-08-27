import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
from scripts.package_skill import _plan_files, package_skill  # noqa: E402


def make_skill(tmp: Path) -> Path:
    skill = tmp / "my-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "tests").mkdir()
    (skill / "SKILL.md").write_text("---\nname: my-skill\ndescription: d\n---\nBody\n")
    (skill / "scripts" / "tool.py").write_text("print('hi')\n")
    (skill / "tests" / "test_tool.py").write_text("# test\n")
    return skill


class PlanFilesTest(unittest.TestCase):
    def test_tests_dir_excluded_at_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(Path(tmp))
            included, skipped = _plan_files(skill)
            included_strs = [str(p) for p in included]
            self.assertTrue(any("SKILL.md" in s for s in included_strs))
            self.assertFalse(any("tests" in Path(s).parts for s in included_strs),
                             f"tests/ leaked into package: {included_strs}")

    def test_symlinks_are_skipped_not_dereferenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skill = make_skill(tmp)
            secret = tmp / "outside.txt"
            secret.write_text("outside the skill dir")
            os.symlink(secret, skill / "scripts" / "link.txt")
            included, skipped = _plan_files(skill)
            self.assertFalse(any("link.txt" in str(p) for p in included),
                             "symlink content must not be embedded in the artifact")
            self.assertTrue(any("link.txt" in str(p) for p in skipped))


class OutputPathIsAbsoluteTests(unittest.TestCase):
    """The reported destination must be absolute on BOTH branches.

    A caller may run this script from a shell whose working directory differs from the calling
    agent's, so a relative destination in the result is one the agent cannot act on. The
    no-`--output-dir` branch derives from `skill_path`, which is absolute only because
    `package_skill` resolves it at scripts/package_skill.py:78 -- this pins that, so a later edit
    there cannot silently make it relative. Both tests pass RELATIVE inputs, or they would pass
    against an implementation that never resolved anything.
    """

    def test_default_branch_reports_absolute_path_from_a_relative_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(Path(tmp))
            prev = os.getcwd()
            os.chdir(tmp)               # relative input is the case under test
            try:
                result = package_skill("my-skill", dry_run=True)
            finally:
                os.chdir(prev)          # never leak cwd into the rest of the suite
            self.assertTrue(result.is_absolute(), str(result))

    def test_explicit_output_dir_reports_absolute_path_from_a_relative_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(Path(tmp))
            prev = os.getcwd()
            os.chdir(tmp)               # a RELATIVE output_dir is the case under test
            try:
                result = package_skill(str(skill), output_dir="dist", dry_run=True)
            finally:
                os.chdir(prev)
            self.assertTrue(result.is_absolute(), str(result))


if __name__ == "__main__":
    unittest.main()
