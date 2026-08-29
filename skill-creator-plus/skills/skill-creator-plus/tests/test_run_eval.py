import sys
import unittest
from pathlib import Path

# Insert the SKILL ROOT (parent of scripts/), not scripts/ itself: run_eval.py
# does `from scripts.utils import ...`, which needs the package importable.
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
import os  # noqa: E402
from unittest import mock  # noqa: E402
import json  # noqa: E402
import types  # noqa: E402
from scripts.run_eval import (  # noqa: E402
    classify_invocation,
    run_single_query,
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


def drive(events, installed=frozenset(), clean_hex="a" * 32):
    """Run the REAL run_single_query against canned stream-json, offline.

    No network, no credential, no `claude` binary. Everything below is reachable this way, which
    is why the fix's own behaviour is now testable at all — the first version of these tests
    mocked os.environ and asserted on dicts, and could not see the defect that mattered.
    """
    import scripts.run_eval as m
    r, w = os.pipe()
    os.write(w, ("".join(json.dumps(e) + "\n" for e in events)).encode())
    os.close(w)

    class FakeProc:
        def __init__(self):
            self.stdout = types.SimpleNamespace(fileno=lambda: r, read=lambda: b"")

        def poll(self):
            return None

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    real_popen, real_uuid = m.subprocess.Popen, m.uuid
    m.subprocess.Popen = lambda *a, **k: FakeProc()
    m.uuid = types.SimpleNamespace(uuid4=lambda: types.SimpleNamespace(hex=clean_hex))
    try:
        return m.run_single_query("q", "skill-creator-plus", "d", 5, None, None, installed)
    finally:
        m.subprocess.Popen, m.uuid = real_popen, real_uuid
        os.close(r)


def skill_events(name, shape="stream"):
    """The CLI's real event shape. `--include-partial-messages` is always passed, so the STREAM
    form is what production sees; the assistant form is the fallback that almost never runs."""
    if shape == "stream":
        return [
            {"type": "stream_event", "event": {"type": "content_block_start",
             "content_block": {"type": "tool_use", "name": "Skill"}}},
            {"type": "stream_event", "event": {"type": "content_block_delta",
             "delta": {"type": "input_json_delta",
                       "partial_json": json.dumps({"skill": name})}}},
            {"type": "stream_event", "event": {"type": "content_block_stop"}},
        ]
    return [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}]


CLEAN = "skill-creator-plus-skill-" + "a" * 8
INSTALLED = frozenset({"skill-creator-plus", "skill-creator"})


class HijackDetectionTest(unittest.TestCase):
    """A run that invoked an INSTALLED skill was not measured, and must not be scored.

    THE BUG THESE EXIST FOR: the first version of this detection lived only in the `assistant`
    branch. `run_single_query` always passes `--include-partial-messages`, so the STREAM branch
    reaches a verdict first and the detector never ran on the path production uses. Hijacks were
    scored as plain non-triggers -- the original bug, shipped inside its own fix. The
    "intermittent, 1 in 3" behaviour measured at the time was a race between two return paths, not
    model non-determinism.
    """

    def test_hijack_is_detected_on_the_stream_path(self):
        """The path production actually takes. Fails against the first version of the fix."""
        out = drive(skill_events("skill-creator-plus"), INSTALLED)
        self.assertFalse(out["triggered"])
        self.assertEqual(out["hijacked_by"], "skill-creator-plus")

    def test_hijack_is_detected_on_the_assistant_path(self):
        out = drive(skill_events("skill-creator-plus", "assistant"), INSTALLED)
        self.assertEqual(out["hijacked_by"], "skill-creator-plus")

    def test_hijack_to_a_shorter_installed_name(self):
        """`skill_name in invoked` missed this, and both names are installed on the dev machine."""
        out = drive(skill_events("skill-creator"), INSTALLED)
        self.assertEqual(out["hijacked_by"], "skill-creator")

    def test_hijack_to_a_plugin_qualified_id(self):
        out = drive(skill_events("someplugin:skill-creator-plus"), INSTALLED)
        self.assertEqual(out["hijacked_by"], "someplugin:skill-creator-plus")

    def test_the_synthesized_copy_is_a_trigger_not_a_hijack(self):
        out = drive(skill_events(CLEAN), INSTALLED)
        self.assertTrue(out["triggered"])
        self.assertIsNone(out["hijacked_by"])

    def test_an_unrelated_skill_is_neither(self):
        out = drive(skill_events("totally-unrelated"), INSTALLED)
        self.assertFalse(out["triggered"])
        self.assertIsNone(out["hijacked_by"])


class ClassifyInvocationTest(unittest.TestCase):
    """Membership in the installed set, never a substring of the name under test.

    Substring was wrong in BOTH directions: it missed a hijack to a shorter installed name, and a
    skill called `docs`/`test`/`eval` would match many installed names -- where ONE false hit
    discards every score in the run.
    """

    def test_generic_name_does_not_false_positive(self):
        installed = frozenset({"docs-writer", "test-runner"})
        self.assertEqual(classify_invocation("docs-writer", "docs-skill-x", installed), "hijacked")
        self.assertEqual(classify_invocation("unrelated", "docs-skill-x", installed), "other")

    def test_empty_invocation_is_other(self):
        self.assertEqual(classify_invocation(None, "x", frozenset()), "other")
        self.assertEqual(classify_invocation("", "x", frozenset()), "other")


if __name__ == "__main__":
    unittest.main()
