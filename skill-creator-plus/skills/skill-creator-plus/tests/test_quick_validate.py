import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from quick_validate import validate_skill  # noqa: E402


def _write_skill(tmpdir: Path, frontmatter: str, body: str = "Body.\n") -> Path:
    skill_dir = tmpdir / "sample-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}")
    return skill_dir


class ValidatorFieldsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_valid(self, frontmatter: str):
        ok, msg = validate_skill(_write_skill(self.tmp, frontmatter))
        self.assertTrue(ok, msg)

    def _assert_invalid(self, frontmatter: str, needle: str):
        ok, msg = validate_skill(_write_skill(self.tmp, frontmatter))
        self.assertFalse(ok, f"expected invalid, got: {msg}")
        self.assertIn(needle, msg)

    # Portable spec fields (already accepted; sanity-check)
    def test_accepts_minimal(self):
        self._assert_valid("name: x\ndescription: d")

    # Claude-specific documented fields
    def test_accepts_when_to_use(self):
        self._assert_valid("name: x\ndescription: d\nwhen_to_use: when user says X")

    def test_accepts_model(self):
        self._assert_valid("name: x\ndescription: d\nmodel: inherit")

    def test_accepts_effort_keyword(self):
        self._assert_valid("name: x\ndescription: d\neffort: high")

    def test_accepts_effort_integer(self):
        self._assert_valid("name: x\ndescription: d\neffort: 5000")

    def test_rejects_effort_bad_keyword(self):
        self._assert_invalid("name: x\ndescription: d\neffort: extreme", "effort")

    def test_accepts_agent(self):
        self._assert_valid("name: x\ndescription: d\ncontext: fork\nagent: general-purpose")

    def test_accepts_paths_list(self):
        self._assert_valid("name: x\ndescription: d\npaths:\n  - src/**\n  - docs/*.md")

    def test_accepts_hooks_object(self):
        self._assert_valid("name: x\ndescription: d\nhooks:\n  PreToolUse:\n    - matcher: Bash")

    def test_accepts_shell_interpreter(self):
        self._assert_valid("name: x\ndescription: d\nshell:\n  interpreter: bash")

    def test_rejects_shell_bad_interpreter(self):
        self._assert_invalid("name: x\ndescription: d\nshell:\n  interpreter: fish", "shell")

    # Undocumented-but-functional
    def test_accepts_top_level_version(self):
        self._assert_valid('name: x\ndescription: d\nversion: "1.2.3"')

    def test_accepts_arguments_and_created_by(self):
        self._assert_valid(
            "name: x\ndescription: d\narguments: branch message\ncreated_by: a@b.c"
        )

    # Dead / unknown fields
    def test_still_rejects_unknown_field(self):
        self._assert_invalid(
            "name: x\ndescription: d\nprogressMessage: loading...",
            "progressMessage",
        )

    # Combined listing-entry cap (Claude-specific) — enforced as a hard check
    # because on Claude the runtime truncates any entry over 1,536 chars.
    def test_combined_description_when_to_use_over_cap(self):
        # 1000 + 1000 = 2000, well over 1536
        combined = "a" * 1000
        self._assert_invalid(
            f'name: x\ndescription: "{combined}"\nwhen_to_use: "{combined}"',
            "1536",
        )

    def test_combined_description_when_to_use_boundary_reject(self):
        # 800 + 737 = 1537, should reject (guards against off-by-one / wrong constant)
        desc = "a" * 800
        wtu = "b" * 737
        self._assert_invalid(
            f'name: x\ndescription: "{desc}"\nwhen_to_use: "{wtu}"',
            "1536",
        )

    def test_combined_description_when_to_use_boundary_accept(self):
        # 800 + 736 = 1536, should accept (exactly at the cap)
        desc = "a" * 800
        wtu = "b" * 736
        self._assert_valid(
            f'name: x\ndescription: "{desc}"\nwhen_to_use: "{wtu}"'
        )


if __name__ == "__main__":
    unittest.main()
