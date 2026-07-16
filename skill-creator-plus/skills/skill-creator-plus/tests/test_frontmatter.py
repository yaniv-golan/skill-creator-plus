import re
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from frontmatter import parse, FrontmatterError  # noqa: E402

try:
    import yaml  # ground truth for the differential test (dev/test-only dependency)
except ImportError:
    yaml = None


# Fixtures spanning every construct real SKILL.md frontmatter uses.
CORPUS = [
    'name: my-skill\ndescription: "A skill that does X."',
    "name: x\ndescription: 'quoted: with colon'",
    "name: plaud\nversion: 1.0.0\ndescription: d\nmetadata:\n  requires:\n    bins: []",
    "name: x\ndescription: d\ndisable-model-invocation: true\nuser-invocable: false\neffort: 3",
    "name: x\ndescription: d\npaths:\n  - src/**\n  - '*.py'\nallowed-tools:\n  - Read\n  - Write",
    "name: x\ndescription: d\npaths: [a, b, c]",
    "name: x\ndescription: d\nshell:\n  interpreter: bash",
    "name: x\ndescription: |\n  line one\n  line two\nmodel: inherit",
    "name: x\ndescription: >\n  folded one\n  folded two",
    "name: x\ndescription: |\n  ends with newline\n",
    "name: x\ndescription: d\nagent: ~",
    "name: x\ndescription: d\nmetadata: {}",
    "name: x  # trailing comment\ndescription: d",
    "name: x\ndescription: d\nmetadata:\n  requires:\n    bins: [git, jq]\n  version: 2",
    "name: x\ndescription: |-\n  stripped\n  block",
]


class ParserUnitTests(unittest.TestCase):
    def test_flat_scalars(self):
        self.assertEqual(parse("name: my-skill\ndescription: hello"),
                         {"name": "my-skill", "description": "hello"})

    def test_quoted_preserved_as_string(self):
        self.assertEqual(parse('version: "1.0"')["version"], "1.0")  # quoted stays str
        self.assertEqual(parse("version: 1.0.0")["version"], "1.0.0")  # two dots -> str

    def test_types(self):
        d = parse("b1: true\nb2: false\nn: ~\ni: 42\nf: 3.14")
        self.assertIs(d["b1"], True)
        self.assertIs(d["b2"], False)
        self.assertIsNone(d["n"])
        self.assertEqual(d["i"], 42)
        self.assertEqual(d["f"], 3.14)

    def test_nested_three_levels(self):
        self.assertEqual(parse("metadata:\n  requires:\n    bins: []"),
                         {"metadata": {"requires": {"bins": []}}})

    def test_block_and_flow_sequences(self):
        self.assertEqual(parse("paths:\n  - a\n  - b")["paths"], ["a", "b"])
        self.assertEqual(parse("paths: [a, b]")["paths"], ["a", "b"])
        self.assertEqual(parse("paths: []")["paths"], [])

    def test_block_scalar_literal(self):
        self.assertEqual(parse("d: |\n  a\n  b\nk: v"), {"d": "a\nb\n", "k": "v"})

    def test_rejects_anchor(self):
        with self.assertRaises(FrontmatterError):
            parse("a: &anchor 1\nb: *anchor")

    def test_rejects_tag(self):
        with self.assertRaises(FrontmatterError):
            parse("a: 1\nb: !custom x")

    def test_rejects_nonempty_flow_mapping(self):
        with self.assertRaises(FrontmatterError):
            parse("meta: {a: b}")


@unittest.skipUnless(yaml is not None, "PyYAML not installed (differential test is dev/test-only)")
class DifferentialAgainstPyYAML(unittest.TestCase):
    """Our parser must agree with yaml.safe_load on the supported subset."""

    def test_corpus_matches_pyyaml(self):
        for t in CORPUS:
            with self.subTest(fixture=t[:40]):
                self.assertEqual(parse(t), yaml.safe_load(t))

    def test_repo_skill_md_files_match_pyyaml(self):
        repo_root = Path(__file__).resolve().parents[4]
        found = 0
        for p in repo_root.rglob("SKILL.md"):
            if "/cache/" in str(p) or "/.git/" in str(p):
                continue
            m = re.match(r"^---\n(.*?)\n---", p.read_text(), re.DOTALL)
            if not m:
                continue
            found += 1
            with self.subTest(skill=str(p)):
                self.assertEqual(parse(m.group(1)), yaml.safe_load(m.group(1)))
        self.assertGreater(found, 0, "expected at least one SKILL.md to differential-test")


if __name__ == "__main__":
    unittest.main()
