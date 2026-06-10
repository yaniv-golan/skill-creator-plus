import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from generate_report import generate_html  # noqa: E402


def history_entry(test_results):
    return {
        "iteration": 1,
        "description": "test description",
        "train_passed": 1, "train_failed": 0, "train_total": 1,
        "train_results": [{"query": "q1", "should_trigger": True,
                           "trigger_rate": 1.0, "triggers": 3, "runs": 3, "pass": True}],
        "test_passed": None, "test_failed": None, "test_total": None,
        "test_results": test_results,
        "passed": 1, "failed": 0, "total": 1,
        "results": [{"query": "q1", "should_trigger": True,
                     "trigger_rate": 1.0, "triggers": 3, "runs": 3, "pass": True}],
    }


class HoldoutZeroTest(unittest.TestCase):
    def test_none_test_results_does_not_crash(self):
        # run_loop stores test_results=None when --holdout 0; the key EXISTS,
        # so h.get("test_results", []) returned None and aggregate_runs(None)
        # raised TypeError mid-run.
        data = {
            "original_description": "orig",
            "best_description": "best",
            "best_score": "1/1",
            "iterations_run": 1,
            "holdout": 0,
            "train_size": 1,
            "test_size": 0,
            "history": [history_entry(None)],
        }
        html_out = generate_html(data, auto_refresh=True, skill_name="x")
        self.assertIn("test description", html_out)


if __name__ == "__main__":
    unittest.main()
