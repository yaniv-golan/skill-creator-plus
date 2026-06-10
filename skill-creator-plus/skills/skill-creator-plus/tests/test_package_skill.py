import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
from scripts.package_skill import _plan_files  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
