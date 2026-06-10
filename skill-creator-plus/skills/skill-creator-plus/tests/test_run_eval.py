import sys
import unittest
from pathlib import Path

# Insert the SKILL ROOT (parent of scripts/), not scripts/ itself: run_eval.py
# does `from scripts.utils import ...`, which needs the package importable.
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
from scripts.run_eval import score_queries  # noqa: E402


class ScoreQueriesTest(unittest.TestCase):
    def test_errors_excluded_from_trigger_rate(self):
        eval_set = [{"query": "q1", "should_trigger": True}]
        runs = {"q1": [
            {"triggered": True, "error": None},
            {"triggered": True, "error": None},
            {"triggered": False, "error": "timeout after 30s with no output"},
        ]}
        results, summary = score_queries(eval_set, runs, trigger_threshold=0.5)
        r = results[0]
        self.assertEqual(r["runs"], 2)           # only successful runs counted
        self.assertEqual(r["triggers"], 2)
        self.assertEqual(r["errors"], 1)
        self.assertTrue(r["pass"])               # 2/2 >= 0.5
        self.assertEqual(summary["errored_runs"], 1)
        self.assertEqual(summary["total_runs"], 3)

    def test_all_errors_fails_query_not_scores_it(self):
        eval_set = [{"query": "q1", "should_trigger": False}]
        runs = {"q1": [{"triggered": False, "error": "claude CLI not found on PATH"}] * 3}
        results, summary = score_queries(eval_set, runs, trigger_threshold=0.5)
        r = results[0]
        # Old behavior scored these False → "did not trigger" → PASS for a
        # should-not-trigger query. That's a fabricated pass.
        self.assertFalse(r["pass"])
        self.assertEqual(r["runs"], 0)
        self.assertEqual(summary["errored_runs"], 3)


if __name__ == "__main__":
    unittest.main()
