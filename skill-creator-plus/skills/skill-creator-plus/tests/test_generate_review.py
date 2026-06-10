import json
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


if __name__ == "__main__":
    unittest.main()
