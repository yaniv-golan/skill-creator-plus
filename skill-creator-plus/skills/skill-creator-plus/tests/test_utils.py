import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
from scripts.utils import DotenvError, load_credentials_from_dotenv  # noqa: E402

NAMES = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
K = "ANTHROPIC_API_KEY"


class DotenvTests(unittest.TestCase):
    def load(self, content, names=NAMES):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            if isinstance(content, str):
                content = content.encode("utf-8")
            p.write_bytes(content)
            return load_credentials_from_dotenv(p, names)

    def test_plain(self):
        self.assertEqual(self.load(f"{K}=abc\n"), {K: "abc"})

    def test_bom(self):
        self.assertEqual(self.load(b"\xef\xbb\xbf" + f"{K}=abc\n".encode()), {K: "abc"})

    def test_crlf(self):
        self.assertEqual(self.load(f"{K}=abc\r\nOTHER=x\r\n"), {K: "abc"})

    def test_export_prefix(self):
        self.assertEqual(self.load(f"export {K}=abc\n"), {K: "abc"})

    def test_spaces_around_equals(self):
        self.assertEqual(self.load(f"{K} =  abc  \n"), {K: "abc"})

    def test_inline_comment_unquoted(self):
        self.assertEqual(self.load(f"{K}=abc # note\n"), {K: "abc"})
        self.assertEqual(self.load(f"{K}=ab#c\n"), {K: "ab#c"})

    def test_quoted_hash_and_backslash_literal(self):
        self.assertEqual(self.load(f'{K}="a # b\\n"\n'), {K: "a # b\\n"})
        self.assertEqual(self.load(f"{K}='a#b' # c\n"), {K: "a#b"})

    def test_trailing_text_after_quote_is_error(self):
        with self.assertRaises(DotenvError):
            self.load(f'{K}="abc" junk\n')

    def test_unterminated_quote_is_error(self):
        with self.assertRaises(DotenvError):
            self.load(f'{K}="abc\n')

    def test_last_wins(self):
        self.assertEqual(self.load(f"{K}=one\n{K}=two\n"), {K: "two"})

    def test_empty_is_absent(self):
        self.assertEqual(self.load(f"{K}=\n"), {})
        self.assertEqual(self.load(f'{K}=""\n'), {})
        self.assertEqual(self.load(f"{K}=one\n{K}=\n"), {})

    def test_unwanted_multiline_value_skipped(self):
        content = (
            'PEM="-----BEGIN KEY-----\nabc=def\n"unterminated\n-----END KEY-----\n'
            f"{K}=ok\n"
        )
        self.assertEqual(self.load(content), {K: "ok"})

    def test_only_wanted_names_returned(self):
        self.assertEqual(self.load(f"{K}=a\nCLAUDE_CODE_OAUTH_TOKEN=b\n", names=(K,)), {K: "a"})

    def test_error_has_line_number_not_secret(self):
        with self.assertRaises(DotenvError) as cm:
            self.load(f'# c\n{K}="sekrit-value-123\n')
        msg = str(cm.exception)
        self.assertIn("2", msg)
        self.assertNotIn("sekrit", msg)
        with self.assertRaises(DotenvError) as cm:
            self.load(f'\n\n{K}="sekrit-value-123" tail\n')
        self.assertIn("3", str(cm.exception))
        self.assertNotIn("sekrit", str(cm.exception))

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(DotenvError):
                load_credentials_from_dotenv(Path(d) / "nope.env", NAMES)


if __name__ == "__main__":
    unittest.main()
