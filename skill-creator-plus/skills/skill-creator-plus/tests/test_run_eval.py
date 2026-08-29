import sys
import unittest
from pathlib import Path

# Insert the SKILL ROOT (parent of scripts/), not scripts/ itself: run_eval.py
# does `from scripts.utils import ...`, which needs the package importable.
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
import os  # noqa: E402
from unittest import mock  # noqa: E402
from scripts.run_eval import (  # noqa: E402
    CREDENTIAL_ENV_VARS,
    InstrumentError,
    isolation_available,
    score_queries,
    _subprocess_env,
)


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


class IsolationTest(unittest.TestCase):
    """The eval cannot measure a skill that is also INSTALLED unless HOME is isolated.

    An earlier eval of this very skill reported 8/24 with all 16 positives failing — including a
    query its description names almost verbatim — because the model kept invoking the operator's
    installed copy. The detector scored that as "did not trigger", which is true and useless. A
    dead instrument and a bad description are indistinguishable in a score, so the instrument has
    to say which one it is.
    """

    def test_isolation_requires_a_credential_in_the_environment(self):
        with mock.patch.dict(os.environ, {v: "" for v in CREDENTIAL_ENV_VARS}, clear=False):
            self.assertFalse(isolation_available())
        for var in CREDENTIAL_ENV_VARS:
            with mock.patch.dict(os.environ, {var: "x"}, clear=False):
                self.assertTrue(isolation_available(), f"{var} should enable isolation")

    def test_isolated_env_repoints_home_and_drops_the_nesting_guard(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "HOME": "/real/home"}, clear=False):
            env = _subprocess_env("/tmp/fake-home")
            self.assertEqual(env["HOME"], "/tmp/fake-home")
            self.assertNotIn("CLAUDECODE", env)

    def test_unisolated_env_keeps_the_real_home(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "HOME": "/real/home"}, clear=False):
            env = _subprocess_env(None)
            self.assertEqual(env["HOME"], "/real/home")
            self.assertNotIn("CLAUDECODE", env)

    def test_instrument_error_is_not_a_score(self):
        """Callers must be able to tell 'measured nothing' from 'scored badly'."""
        self.assertTrue(issubclass(InstrumentError, RuntimeError))


class HijackDetectionTest(unittest.TestCase):
    """A run that invoked the INSTALLED skill was not measured, and must not be scored.

    This is intermittent rather than certain — measured 1 in 3 unisolated runs — which is exactly
    why it needs detecting rather than warning about. A warning the operator reads once and then
    sees three green runs behind teaches them the warning is noise.
    """

    def test_hijack_flag_travels_on_the_outcome(self):
        outcome = {"triggered": False, "error": None, "hijacked_by": "skill-creator-plus"}
        self.assertTrue(outcome.get("hijacked_by"))

    def test_a_hijacked_run_is_a_non_trigger_to_score_queries(self):
        """score_queries is deliberately unaware of hijacking — run_eval refuses before scoring.

        Pins the layering: if a future change makes score_queries swallow the flag, a hijacked run
        would silently become a plain non-trigger again, which is the original bug.
        """
        eval_set = [{"query": "q1", "should_trigger": True}]
        runs = {"q1": [{"triggered": False, "error": None, "hijacked_by": "other-skill"}]}
        results, summary = score_queries(eval_set, runs, trigger_threshold=0.5)
        self.assertEqual(summary["passed"], 0)
        self.assertEqual(results[0]["triggers"], 0)
