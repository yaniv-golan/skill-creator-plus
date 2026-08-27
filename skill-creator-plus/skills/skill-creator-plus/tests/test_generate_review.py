import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VIEWER_DIR = Path(__file__).resolve().parent.parent / "eval-viewer"
sys.path.insert(0, str(VIEWER_DIR))
from generate_review import find_runs, generate_html  # noqa: E402


class FindRunsSortTest(unittest.TestCase):
    def test_mixed_eval_id_presence_does_not_crash(self):
        # One run has eval_metadata.json with an int eval_id, the other has
        # none (eval_id=None). sorted() compared None with int -> TypeError.
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "a" / "outputs").mkdir(parents=True)
            (ws / "b" / "outputs").mkdir(parents=True)
            (ws / "b" / "eval_metadata.json").write_text(
                json.dumps({"eval_id": 1, "prompt": "p"}))
            runs = find_runs(ws)  # must not raise
            self.assertEqual(len(runs), 2)
            # Runs with a real eval_id sort before metadata-less runs.
            self.assertEqual(runs[0]["eval_id"], 1)


class EscapingTest(unittest.TestCase):
    def test_no_raw_angle_brackets_in_embedded_json(self):
        hostile = "</script><script>alert(1)</script><!-- <script"
        runs = [{"id": "r1", "prompt": hostile, "eval_id": 0,
                 "outputs": [{"name": "o.html", "type": "text", "content": hostile}],
                 "grading": None}]
        html_out = generate_html(runs, "x", is_static=True)
        data_line = next(l for l in html_out.splitlines() if "EMBEDDED_DATA" in l)
        self.assertNotIn("</script>", data_line)
        self.assertNotIn("<!--", data_line)
        self.assertNotIn("<script", data_line)


class StaticPathIsReportedAbsoluteTests(unittest.TestCase):
    """`--static` must echo the RESOLVED path.

    A relative --static under a sandboxed runtime resolves against the shell's cwd, which is not
    the one the calling agent's file tools use; echoing the raw input hides where the bytes went.
    Uses a relative input, or it would pass against an implementation that never resolved.
    """

    def test_static_output_line_is_absolute(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "a" / "outputs").mkdir(parents=True)   # generate_review exits early with no runs
            prev = os.getcwd()
            os.chdir(tmp)
            try:
                proc = subprocess.run(
                    [sys.executable, str(VIEWER_DIR / "generate_review.py"),
                     str(ws), "--static", "out.html"],   # RELATIVE --static is the case under test
                    capture_output=True, text=True, timeout=120,
                )
            finally:
                os.chdir(prev)
            line = [l for l in proc.stdout.splitlines() if "Static viewer written to:" in l]
            self.assertTrue(line, f"no static-write line in stdout:\n{proc.stdout}\n{proc.stderr}")
            reported = line[0].split("written to:", 1)[1].strip()
            self.assertTrue(Path(reported).is_absolute(), reported)


if __name__ == "__main__":
    unittest.main()
