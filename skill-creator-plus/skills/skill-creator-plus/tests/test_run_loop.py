import sys
import unittest
from pathlib import Path

# Insert the SKILL ROOT (parent of scripts/): run_loop.py does
# `from scripts...` imports, which need the package importable.
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
from scripts.run_loop import split_eval_set  # noqa: E402


def evals(n_trigger, n_no_trigger):
    return ([{"query": f"t{i}", "should_trigger": True} for i in range(n_trigger)] +
            [{"query": f"n{i}", "should_trigger": False} for i in range(n_no_trigger)])


class SplitTest(unittest.TestCase):
    def test_tiny_eval_set_raises_instead_of_empty_train(self):
        # 1 positive + 1 negative with holdout=0.4: max(1, ...) puts both in
        # test, leaving train empty — the loop then "passes" iteration 1
        # vacuously and silently skips optimization.
        with self.assertRaises(ValueError):
            split_eval_set(evals(1, 1), holdout=0.4)

    def test_normal_split_is_unchanged(self):
        train, test = split_eval_set(evals(5, 5), holdout=0.4)
        self.assertTrue(train)
        self.assertTrue(test)
        self.assertEqual(len(train) + len(test), 10)


if __name__ == "__main__":
    unittest.main()
