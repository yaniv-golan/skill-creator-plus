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


def drive(events, installed=frozenset(), clean_hex="a" * 32, exit_code=None, tail=(),
          polls_before_exit=None, timeout=5):
    """Run the REAL run_single_query against canned stream-json, offline.

    No network, no credential, no `claude` binary. Everything below is reachable this way, which
    is why the fix's own behaviour is now testable at all — the first version of these tests
    mocked os.environ and asserted on dicts, and could not see the defect that mattered.

    Default: the pipe holds `events`, then EOF while the process is still "alive" -- the run ends
    with was_killed True, i.e. a timeout. With `exit_code` the fake process exits by itself: poll()
    is None for `polls_before_exit` calls (default 1 when there are events, so they are read from
    the pipe first, else 0) and then returns the code, and stdout.read() hands back `tail` (a list
    of event dicts, or a raw str/bytes for an unterminated line) -- the self-exit branch.
    """
    import scripts.run_eval as m
    r, w = os.pipe()
    os.write(w, ("".join(json.dumps(e) + "\n" for e in events)).encode())
    os.close(w)

    if isinstance(tail, (str, bytes)):
        tail_bytes = tail.encode() if isinstance(tail, str) else tail
    else:
        tail_bytes = "".join(json.dumps(e) + "\n" for e in tail).encode()
    if polls_before_exit is None:
        polls_before_exit = 1 if events else 0

    class FakeProc:
        def __init__(self):
            self.polls = 0
            self.stdout = types.SimpleNamespace(fileno=lambda: r, read=self._read)

        def _read(self):
            out, self._tail = getattr(self, "_tail", tail_bytes), b""
            return out

        def poll(self):
            if exit_code is None:
                return None
            self.polls += 1
            return None if self.polls <= polls_before_exit else exit_code

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    real_popen, real_uuid = m.subprocess.Popen, m.uuid
    m.subprocess.Popen = lambda *a, **k: FakeProc()
    m.uuid = types.SimpleNamespace(uuid4=lambda: types.SimpleNamespace(hex=clean_hex))
    try:
        return m.run_single_query("q", "skill-creator-plus", "d", timeout, None, None, installed)
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


# Event shapes below are trimmed from a real CLI (2.1.322) run: a bogus ANTHROPIC_API_KEY, no
# credential at all, and a refused connection.
INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5-5"}
STATUS = {"type": "system", "subtype": "status", "status": "requesting"}
SYNTH = {"model": "<synthetic>", "role": "assistant", "stop_reason": "stop_sequence",
         "content": [{"type": "text", "text": "Invalid API key \u00b7 Fix external API key"}]}
A401 = {"type": "assistant", "message": SYNTH, "error": "authentication_failed",
        "is_api_error_message": True, "api_error_status": 401}
R401 = {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 401,
        "terminal_reason": "api_error", "result": "Invalid API key \u00b7 Fix external API key"}
A_NOCRED = {"type": "assistant", "error": "authentication_failed", "is_api_error_message": True,
            "message": {**SYNTH, "content": [{"type": "text",
                                              "text": "Not logged in \u00b7 Please run /login"}]}}
R_NOCRED = {"type": "result", "subtype": "success", "is_error": True, "api_error_status": None,
            "result": "Not logged in \u00b7 Please run /login"}


def retry(status=None, error="unknown", attempt=1):
    return {"type": "system", "subtype": "api_retry", "attempt": attempt, "max_retries": 10,
            "retry_delay_ms": 500, "error_status": status, "error": error}


def block_start(kind):
    cb = {"type": kind} if kind != "tool_use" else {"type": "tool_use", "name": "Bash"}
    return {"type": "stream_event", "event": {"type": "content_block_start", "content_block": cb}}


def text_delta(t="hello"):
    return {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": t}}}


def pending_skill_start():
    return {"type": "stream_event", "event": {"type": "content_block_start",
            "content_block": {"type": "tool_use", "name": "Skill"}}}


def partial_delta(fragment):
    return {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": fragment}}}


class ApiErrorScoringTest(unittest.TestCase):
    """Item 0: an API error is an errored run, never a clean non-trigger.

    One test per row of the end-of-run decision table (comments name the row), plus the streaming
    returns and the edges around them.
    """

    def setUp(self):
        p = mock.patch.dict(os.environ, {v: "" for v in CREDENTIAL_ENV_VARS + ("ANTHROPIC_BASE_URL",)})
        p.start()
        self.addCleanup(p.stop)

    def assertErrored(self, out, *fragments):
        self.assertFalse(out["triggered"])
        self.assertTrue(out["error"], out)
        for f in fragments:
            self.assertIn(f, out["error"])
        self.assertNotIn("None", out["error"])

    def assertCleanNonTrigger(self, out):
        self.assertFalse(out["triggered"])
        self.assertIsNone(out["error"])

    # --- immediate errored returns while streaming
    def test_result_is_error_with_success_subtype_is_errored(self):
        out = drive([INIT, R401])
        self.assertErrored(out, "api error 401", "Invalid API key")
        self.assertEqual(out["api_status"], 401)

    def test_assistant_with_top_level_error_is_errored(self):
        out = drive([INIT, STATUS, A401, R401])
        self.assertErrored(out, "api error 401")
        self.assertEqual(out["api_error"], "authentication_failed")

    def test_clean_result_is_still_a_clean_non_trigger(self):
        out = drive([INIT, {"type": "result", "subtype": "success", "is_error": False}])
        self.assertCleanNonTrigger(out)

    # --- row 2 plus the post-exit tail
    def test_401_delivered_only_in_the_post_exit_tail_without_earlier_events(self):
        out = drive([], exit_code=1, tail=[INIT, STATUS, A401, R401])
        self.assertErrored(out, "api error 401")

    def test_401_delivered_only_in_the_post_exit_tail_after_earlier_events(self):
        out = drive([INIT, STATUS], exit_code=1, tail=[A401, R401])
        self.assertErrored(out, "api error 401")

    def test_final_unterminated_line_is_parsed(self):
        out = drive([INIT], exit_code=1, tail=json.dumps(R401))
        self.assertErrored(out, "api error 401")

    def test_row2_nonzero_exit_with_no_error_event(self):
        out = drive([INIT, STATUS], exit_code=2)
        self.assertErrored(out, "claude exited with code 2")

    def test_row2_nonzero_exit_before_any_output(self):
        out = drive([], exit_code=1)
        self.assertErrored(out, "claude exited with code 1 before any output")

    def test_row2_names_the_last_api_retry_error(self):
        out = drive([INIT, retry(529, "overloaded")], exit_code=1)
        self.assertErrored(out, "claude exited with code 1", "529")

    # --- row 1
    def test_row1_pending_skill_call_then_end(self):
        out = drive([pending_skill_start(), partial_delta('{"ski')])
        self.assertErrored(out, "mid tool call")

    def test_row1_pending_skill_call_then_clean_exit(self):
        out = drive([pending_skill_start(), partial_delta('{"ski')], exit_code=0)
        self.assertErrored(out, "mid tool call")

    # --- row 3
    def test_row3_init_and_retry_then_timeout(self):
        out = drive([INIT, retry(429, "rate_limit")])
        self.assertErrored(out, "api error 429", "retrying")

    def test_row3_text_then_retry_then_timeout_last_event_wins(self):
        out = drive([INIT, block_start("text"), text_delta(), retry(529, "overloaded")])
        self.assertErrored(out, "api error 529")

    def test_row3_connection_failure_has_null_status_and_no_credential_blame(self):
        out = drive([INIT, STATUS, retry(None, "unknown", 1), retry(None, "unknown", 2)])
        self.assertErrored(out, "api error (unknown)")
        self.assertIsNone(out["api_status"])

    # --- row 5 vs row 4
    def test_row5_retry_then_recovered_text_then_timeout_is_clean(self):
        out = drive([INIT, retry(429, "rate_limit"), block_start("text"), text_delta()])
        self.assertCleanNonTrigger(out)

    def test_row5_text_then_timeout_is_a_clean_non_trigger(self):
        out = drive([INIT, block_start("text"), text_delta("a"), text_delta("b")])
        self.assertCleanNonTrigger(out)

    def test_row5_status_event_after_text_does_not_turn_it_into_an_error(self):
        # A status/hook system event mid-answer is bookkeeping; the long-answer timeout must stay
        # a clean non-trigger rather than fall into row 4.
        out = drive([INIT, block_start("text"), text_delta("a"), STATUS, text_delta("b")])
        self.assertCleanNonTrigger(out)

    def test_row4_init_then_timeout(self):
        out = drive([INIT, STATUS])
        self.assertErrored(out, "timeout", "before answer text")

    def test_row4_thinking_only_then_timeout(self):
        out = drive([INIT, block_start("thinking")])
        self.assertErrored(out, "timeout", "mid-thinking")

    def test_row4_no_events_at_all_keeps_the_no_output_message(self):
        out = drive([])
        self.assertErrored(out, "no output from claude")

    # --- row 6
    def test_row6_text_then_clean_exit_without_a_result(self):
        out = drive([INIT, block_start("text"), text_delta()], exit_code=0)
        self.assertErrored(out, "without a result")

    # --- not model output
    def test_synthetic_assistant_without_error_is_not_model_output(self):
        out = drive([INIT, {"type": "assistant", "message": SYNTH}])
        self.assertErrored(out, "timeout")

    # --- null statuses
    def test_null_api_error_status_has_no_None_and_no_credential_claim(self):
        out = drive([INIT, A_NOCRED, R_NOCRED])
        self.assertErrored(out, "api error (authentication_failed)")
        self.assertIsNone(out["api_status"])
        out = drive([INIT, R_NOCRED])
        self.assertErrored(out, "api error (")

    # --- regression guards: unchanged early returns
    def test_real_skill_trigger_still_returns_triggered(self):
        out = drive(skill_events(CLEAN))
        self.assertTrue(out["triggered"])
        self.assertIsNone(out["error"])

    def test_non_skill_tool_use_still_a_clean_non_trigger(self):
        out = drive([INIT, block_start("tool_use")])
        self.assertCleanNonTrigger(out)

    def test_message_stop_still_a_clean_non_trigger(self):
        out = drive([INIT, block_start("text"),
                     {"type": "stream_event", "event": {"type": "message_stop"}}])
        self.assertCleanNonTrigger(out)


class CanaryErrorTest(unittest.TestCase):
    """The canary names the credential only when the API rejected it."""

    def setUp(self):
        p = mock.patch.dict(os.environ, {v: "" for v in CREDENTIAL_ENV_VARS + ("ANTHROPIC_BASE_URL",)})
        p.start()
        self.addCleanup(p.stop)

    def run_inner(self, canary, env=None):
        import scripts.run_eval as m
        with mock.patch.dict(os.environ, env or {}), \
                mock.patch.object(m, "run_canary", return_value=canary), \
                mock.patch.object(m, "installed_skill_names", return_value=set()):
            with self.assertRaises(InstrumentError) as cm:
                m._run_eval_inner([], "s", "d", 1, 5, 1, 0.5, None, None)
        return str(cm.exception)

    def test_canary_401_names_credentials_by_name_only(self):
        canary = drive([INIT, A401, R401])
        msg = self.run_inner(canary, {"ANTHROPIC_API_KEY": "sk-secret-value"})
        self.assertIn("CANARY ERRORED", msg)
        self.assertIn("api error 401", msg)
        self.assertIn("ANTHROPIC_API_KEY", msg)
        self.assertNotIn("sk-secret-value", msg)

    def test_canary_authentication_failed_with_null_status_and_no_credential(self):
        msg = self.run_inner(drive([INIT, A_NOCRED, R_NOCRED]))
        self.assertIn("CANARY ERRORED", msg)
        self.assertIn("none of", msg)

    def test_canary_cli_not_found_is_neutral(self):
        msg = self.run_inner({"triggered": False, "error": "claude CLI not found on PATH"},
                             {"ANTHROPIC_API_KEY": "x"})
        self.assertIn("CANARY FAILED", msg)
        self.assertNotIn("CANARY ERRORED", msg)

    def test_canary_connection_failure_is_neutral(self):
        canary = drive([INIT, STATUS, retry(None, "unknown")])
        msg = self.run_inner(canary, {"ANTHROPIC_API_KEY": "x"})
        self.assertIn("CANARY FAILED", msg)
        self.assertIn("api error (unknown)", msg)
        self.assertNotIn("CANARY ERRORED", msg)

    def test_credential_names_helper_reads_environ_and_extra_env(self):
        from scripts.run_eval import credential_names_present
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}):
            self.assertEqual(credential_names_present(), ["CLAUDE_CODE_OAUTH_TOKEN"])
            self.assertEqual(credential_names_present({"ANTHROPIC_API_KEY": "k"}),
                             ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"])


class SlashQueryWarningTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {v: "" for v in CREDENTIAL_ENV_VARS + ("ANTHROPIC_BASE_URL",)})
        p.start()
        self.addCleanup(p.stop)

    def test_slash_prefixed_query_warns_on_stderr_without_failing(self):
        import contextlib
        import io
        import tempfile
        import scripts.run_eval as m
        with tempfile.TemporaryDirectory() as d:
            skill = Path(d) / "s"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: s\ndescription: does things\n---\nbody\n")
            ev = Path(d) / "ev.json"
            ev.write_text(json.dumps([{"query": "/cost", "should_trigger": True},
                                      {"query": "plain", "should_trigger": False}]))
            fake = {"results": [], "summary": {"errored_runs": 0, "total_runs": 2,
                                               "passed": 0, "total": 0, "failed": 0}}
            err, out = io.StringIO(), io.StringIO()
            argv = ["run_eval", "--eval-set", str(ev), "--skill-path", str(skill)]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(m, "run_eval", return_value=fake), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                m.main()
        self.assertIn("starts with '/'", err.getvalue())
        self.assertIn("/cost", err.getvalue())
        self.assertNotIn("plain", err.getvalue())


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
