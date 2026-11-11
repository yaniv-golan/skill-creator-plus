"""Compare mode, duplicate-query rejection, --dotenv wiring (extra_env) and the improver guard.

Everything is offline: run_eval and subprocess.Popen are mocked, no credential is real, and
os.environ is only ever patched through mock.patch.dict (never mutated).
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
import scripts.run_eval as m  # noqa: E402
from scripts.run_eval import (  # noqa: E402
    CREDENTIAL_ENV_VARS, InstrumentError, compare_results, find_duplicate_queries,
    isolation_available, _subprocess_env,
)

CLEAN_ENV = {v: "" for v in CREDENTIAL_ENV_VARS + ("ANTHROPIC_BASE_URL",)}
SECRET = "sk-ant-TESTSECRET-0123456789"


def row(triggers, runs, should_trigger=True, errors=0, query="q", threshold=0.5):
    rate = triggers / runs if runs else 0.0
    ok = (rate >= threshold) if should_trigger else (rate < threshold)
    return {"query": query, "should_trigger": should_trigger, "trigger_rate": rate,
            "triggers": triggers, "runs": runs, "errors": errors, "error_messages": [],
            "pass": ok if runs else False}


def result(rows, errored_runs=0, total_runs=None):
    total = total_runs if total_runs is not None else sum(r["runs"] + r["errors"] for r in rows)
    return {"skill_name": "sk", "description": "d", "isolated": True,
            "canary": {"triggered": True, "hijacked_by": None}, "results": rows,
            "summary": {"total": len(rows), "passed": sum(r["pass"] for r in rows),
                        "failed": sum(not r["pass"] for r in rows),
                        "errored_runs": errored_runs, "total_runs": total}}


def change(b, c, should_trigger=True):
    out = compare_results(result([row(*b, should_trigger=should_trigger)]),
                          result([row(*c, should_trigger=should_trigger)]))
    return out["rows"][0]["change"]


class CompareResultsTest(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(change((0, 3), (3, 3)), "fixed")

    def test_regressed(self):
        self.assertEqual(change((3, 3), (0, 3)), "regressed")

    def test_same_when_no_flip_even_if_rate_moved(self):
        # should-not-trigger 0/3 -> 1/3 stays below threshold: no flip, shown as same
        self.assertEqual(change((0, 3), (1, 3), should_trigger=False), "same")

    def test_within_noise_when_count_differs_by_one(self):
        # threshold 0.5 at n=2: 1/2 passes, 0/2 fails -- a one-run flip
        self.assertEqual(change((0, 2), (1, 2)), "within_noise")

    def test_within_noise_when_usable_counts_differ(self):
        self.assertEqual(change((0, 3), (4, 4)), "within_noise")

    def test_within_noise_when_swing_under_half_of_n(self):
        # n=10: 4/10 fails, 6/10 passes; swing 2 is under half of 10 and not under 2
        self.assertEqual(change((4, 10), (6, 10)), "within_noise")

    def test_errored_beats_a_flip(self):
        self.assertEqual(change((0, 0), (3, 3)), "errored")
        self.assertEqual(change((3, 3), (0, 0)), "errored")

    def test_runs_1_every_flip_is_noise(self):
        self.assertEqual(change((0, 1), (1, 1)), "within_noise")
        self.assertEqual(change((1, 1), (0, 1)), "within_noise")

    def test_runs_2(self):
        self.assertEqual(change((0, 2), (2, 2)), "fixed")
        self.assertEqual(change((2, 2), (0, 2)), "regressed")

    def test_runs_3(self):
        self.assertEqual(change((0, 3), (2, 3)), "fixed")
        self.assertEqual(change((1, 3), (3, 3)), "fixed")
        self.assertEqual(change((1, 3), (2, 3)), "within_noise")

    def test_runs_10_two_to_seven_is_a_change(self):
        # float 0.7-0.2 is 0.49999...; integer math must call this a change
        self.assertEqual(change((2, 10), (7, 10)), "fixed")
        self.assertEqual(change((7, 10), (2, 10)), "regressed")

    def test_row_schema_and_summary(self):
        b = result([row(0, 3, query="a"), row(3, 3, query="b"), row(0, 3, query="c", should_trigger=False)])
        c = result([row(3, 3, query="a"), row(0, 3, query="b"), row(0, 3, query="c", should_trigger=False)])
        out = compare_results(b, c)
        self.assertEqual([r["change"] for r in out["rows"]], ["fixed", "regressed", "same"])
        self.assertEqual(set(out["rows"][0]), {
            "query", "should_trigger", "baseline_triggers", "baseline_usable", "baseline_errors",
            "candidate_triggers", "candidate_usable", "candidate_errors", "baseline_pass",
            "candidate_pass", "change"})
        s = out["summary"]
        self.assertEqual((s["fixed"], s["regressed"], s["same"], s["within_noise"], s["errored"]),
                         (1, 1, 1, 0, 0))
        self.assertEqual((s["baseline_passed"], s["candidate_passed"]), (2, 2))


class DuplicateQueryTest(unittest.TestCase):
    def test_helper_names_duplicates_once(self):
        es = [{"query": "a"}, {"query": "b"}, {"query": "a"}, {"query": "a"}]
        self.assertEqual(find_duplicate_queries(es), ["a"])

    def test_non_list_is_ignored(self):
        self.assertEqual(find_duplicate_queries({"queries": []}), [])


def make_skill(tmp: Path) -> Path:
    skill = tmp / "sk"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: sk\ndescription: cand desc\n---\nBody\n")
    return skill


def run_main(argv, run_eval_mock=None, env=None):
    """Run run_eval.main() in process; returns (exit code or None, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = None
    patches = [mock.patch.dict(os.environ, {**CLEAN_ENV, **(env or {})}),
               mock.patch.object(sys, "argv", ["run_eval"] + argv)]
    if run_eval_mock is not None:
        patches.append(mock.patch.object(m, "run_eval", run_eval_mock))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        try:
            m.main()
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class MainFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.skill = make_skill(self.tmp)
        self.es = self.tmp / "es.json"
        self.es.write_text(json.dumps([
            {"query": "q1", "should_trigger": True}, {"query": "q2", "should_trigger": False}]))
        self.base_argv = ["--eval-set", str(self.es), "--skill-path", str(self.skill)]

    def tearDown(self):
        self._tmp.cleanup()


class DuplicateMainTest(MainFixture):
    def test_duplicates_exit_1_naming_them_in_every_mode(self):
        self.es.write_text(json.dumps([{"query": "dup", "should_trigger": True},
                                       {"query": "dup", "should_trigger": False}]))
        for extra in ([], ["--baseline-description", "old"]):
            called = mock.Mock()
            code, out, err = run_main(self.base_argv + extra, called)
            self.assertEqual(code, 1)
            self.assertIn("'dup'", err)
            called.assert_not_called()


class CompareMainTest(MainFixture):
    def fake(self, descs_to_result):
        calls = []

        def f(**kw):
            calls.append(kw["description"])
            r = descs_to_result[kw["description"]]
            if isinstance(r, Exception):
                raise r
            return r
        f.calls = calls
        return f

    def good(self, b_trig=0, c_trig=3):
        return {"old": result([row(b_trig, 3, query="q1"), row(0, 3, False, query="q2")]),
                "new": result([row(c_trig, 3, query="q1"), row(0, 3, False, query="q2")])}

    def test_output_shape_and_order(self):
        f = self.fake(self.good())
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--description", "new"], f)
        self.assertIsNone(code)
        data = json.loads(out)
        self.assertEqual(set(data), {"mode", "baseline", "candidate", "comparison"})
        self.assertEqual(data["mode"], "compare")
        self.assertEqual(f.calls, ["old", "new"])
        self.assertEqual(data["baseline"]["description"], "d")  # canned, from the mock
        self.assertEqual([r["change"] for r in data["comparison"]["rows"]], ["fixed", "same"])

    def test_candidate_defaults_to_skill_md_description_and_baseline_file(self):
        bf = self.tmp / "old.txt"
        bf.write_text("old\n")
        f = self.fake({"old": result([row(0, 3, query="q1"), row(0, 3, False, query="q2")]),
                       "cand desc": result([row(3, 3, query="q1"), row(0, 3, False, query="q2")])})
        code, out, err = run_main(self.base_argv + ["--baseline-description-file", str(bf)], f)
        self.assertIsNone(code)
        self.assertEqual(f.calls, ["old", "cand desc"])

    def test_verbose_prints_every_row_including_same(self):
        f = self.fake(self.good())
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--description", "new", "--verbose"], f)
        self.assertIn("baseline 0/3 → candidate 3/3  [FIXED]", err)
        self.assertIn("baseline 0/3 → candidate 0/3  [same]", err)

    def test_baseline_failure_exits_4_and_candidate_never_runs(self):
        f = self.fake({"old": InstrumentError("CANARY FAILED x"), "new": result([])})
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--description", "new"], f)
        self.assertEqual(code, 4)
        self.assertEqual(f.calls, ["old"])
        self.assertIn("baseline: CANARY FAILED x", err)
        self.assertEqual(out, "")

    def test_candidate_failure_prints_baseline_first_then_exits_4(self):
        g = self.good()
        f = self.fake({"old": g["old"], "new": InstrumentError("HIJACKED y")})
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--description", "new"], f)
        self.assertEqual(code, 4)
        data = json.loads(out)
        self.assertEqual(data["mode"], "compare")
        self.assertIsNone(data["candidate"])
        self.assertIsNone(data["comparison"])
        self.assertEqual(data["baseline"], g["old"])
        self.assertIn("candidate: HIJACKED y", err)

    def test_baseline_flags_are_mutually_exclusive(self):
        f = self.fake(self.good())
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--baseline-description-file", "x"], f)
        self.assertEqual(code, 2)
        self.assertIn("not allowed with", err)
        self.assertEqual(f.calls, [])

    def test_every_run_errored_in_either_arm_exits_1_after_printing_json(self):
        dead = result([row(0, 0, errors=3, query="q1"), row(0, 0, errors=3, query="q2")],
                      errored_runs=6, total_runs=6)
        f = self.fake({"old": self.good()["old"], "new": dead})
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--description", "new"], f)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["mode"], "compare")
        self.assertIn("candidate: every run errored", err)

    def test_unisolated_warning_printed_once_in_compare_mode(self):
        f = self.fake(self.good())
        code, out, err = run_main(self.base_argv + ["--baseline-description", "old",
                                                    "--description", "new"], f)
        self.assertEqual(err.count("no credential in"), 1)

    def test_unisolated_warning_printed_once_without_compare(self):
        f = self.fake({"cand desc": self.good()["new"]})
        code, out, err = run_main(self.base_argv, f)
        self.assertEqual(err.count("no credential in"), 1)

    def test_no_warning_when_a_credential_is_set(self):
        f = self.fake({"cand desc": self.good()["new"]})
        code, out, err = run_main(self.base_argv, f, env={"ANTHROPIC_API_KEY": "x"})
        self.assertNotIn("no credential in", err)

    def test_no_flag_output_shape_is_unchanged(self):
        r = self.good()["new"]
        f = self.fake({"cand desc": r})
        code, out, err = run_main(self.base_argv, f)
        self.assertIsNone(code)
        self.assertEqual(json.loads(out), r)
        self.assertNotIn("mode", json.loads(out))


class ExtraEnvTest(unittest.TestCase):
    def test_subprocess_env_merges_extra_env_without_touching_os_environ(self):
        with mock.patch.dict(os.environ, CLEAN_ENV):
            before = dict(os.environ)
            env = _subprocess_env("/tmp/h", {"ANTHROPIC_API_KEY": SECRET})
            self.assertEqual(env["ANTHROPIC_API_KEY"], SECRET)
            self.assertEqual(env["HOME"], "/tmp/h")
            self.assertEqual(dict(os.environ), before)
            self.assertNotEqual(os.environ.get("ANTHROPIC_API_KEY"), SECRET)

    def test_isolation_available_counts_extra_env(self):
        with mock.patch.dict(os.environ, CLEAN_ENV):
            self.assertFalse(isolation_available())
            self.assertFalse(isolation_available({}))
            self.assertTrue(isolation_available({"CLAUDE_CODE_OAUTH_TOKEN": "t"}))

    def test_extra_env_reaches_the_child_through_run_eval(self):
        seen = []

        def fake_popen(cmd, **kw):
            seen.append(kw["env"])
            raise FileNotFoundError

        with mock.patch.dict(os.environ, CLEAN_ENV), \
                mock.patch.object(m.subprocess, "Popen", fake_popen):
            before = dict(os.environ)
            with self.assertRaises(InstrumentError):
                m.run_eval([{"query": "q", "should_trigger": True}], "sk", "d", 1, 1,
                           extra_env={"ANTHROPIC_API_KEY": SECRET})
            self.assertEqual(dict(os.environ), before)
        self.assertTrue(seen)
        self.assertEqual(seen[0]["ANTHROPIC_API_KEY"], SECRET)
        self.assertNotEqual(seen[0]["HOME"], os.environ.get("HOME"), "isolated HOME expected")

    def test_canary_401_names_extra_env_credential_by_name_only(self):
        res = {"triggered": False, "error": "api error 401: bad", "api_status": 401,
               "api_error": "authentication_failed", "hijacked_by": None}
        with mock.patch.dict(os.environ, CLEAN_ENV), \
                mock.patch.object(m, "run_canary", return_value=res):
            with self.assertRaises(InstrumentError) as cm:
                m._run_eval_inner([], "sk", "d", 1, 1, 1, 0.5, None, "/tmp/h",
                                  {"ANTHROPIC_API_KEY": SECRET})
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))


class DotenvMainTest(MainFixture):
    def env_file(self, text):
        p = self.tmp / ".env"
        p.write_text(text)
        return str(p)

    def test_leak_check_secret_never_reaches_stdout_or_stderr(self):
        envs = []

        def fake_popen(cmd, **kw):
            envs.append(kw["env"])
            raise FileNotFoundError

        with mock.patch.object(m.subprocess, "Popen", fake_popen):
            code, out, err = run_main(
                self.base_argv + ["--dotenv", self.env_file(f"ANTHROPIC_API_KEY={SECRET}\n"),
                                  "--verbose"])
        self.assertEqual(code, 4)  # canary could not run
        self.assertEqual(envs[0]["ANTHROPIC_API_KEY"], SECRET)  # the child did get it
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)
        self.assertIn("dotenv: loaded ANTHROPIC_API_KEY; kept existing none; "
                      "eval children see ANTHROPIC_API_KEY", err)

    def test_dotenv_key_loads_only_the_named_credential(self):
        # A file with both credentials hands both to the children, and the CLI prefers the API key;
        # a stale key beside a valid OAuth token made every run 401 (measured). --dotenv-key picks one.
        envs = []

        def fake_popen(cmd, **kw):
            envs.append(kw["env"])
            raise FileNotFoundError

        text = f"ANTHROPIC_API_KEY=stale-{SECRET}\nCLAUDE_CODE_OAUTH_TOKEN={SECRET}\n"
        with mock.patch.object(m.subprocess, "Popen", fake_popen):
            code, out, err = run_main(
                self.base_argv + ["--dotenv", self.env_file(text),
                                  "--dotenv-key", "CLAUDE_CODE_OAUTH_TOKEN"])
        self.assertEqual(code, 4)
        self.assertEqual(envs[0]["CLAUDE_CODE_OAUTH_TOKEN"], SECRET)
        self.assertFalse(envs[0].get("ANTHROPIC_API_KEY"))
        self.assertIn("dotenv: loaded CLAUDE_CODE_OAUTH_TOKEN;", err)
        self.assertNotIn("2 credentials present", err)
        self.assertNotIn(SECRET, out + err)

    def test_dotenv_key_without_dotenv_is_a_usage_error(self):
        code, out, err = run_main(self.base_argv + ["--dotenv-key", "ANTHROPIC_API_KEY"])
        self.assertEqual(code, 2)
        self.assertIn("--dotenv-key needs --dotenv", err)

    def test_dotenv_key_names_the_key_when_the_file_lacks_it(self):
        code, out, err = run_main(
            self.base_argv + ["--dotenv", self.env_file(f"ANTHROPIC_API_KEY={SECRET}\n"),
                              "--dotenv-key", "CLAUDE_CODE_OAUTH_TOKEN"])
        self.assertEqual(code, 1)
        self.assertIn("no CLAUDE_CODE_OAUTH_TOKEN found", err)
        self.assertNotIn(SECRET, out + err)

    def test_missing_file_exits_1_without_secret(self):
        code, out, err = run_main(self.base_argv + ["--dotenv", str(self.tmp / "nope.env")])
        self.assertEqual(code, 1)

    def test_parse_error_exits_1_with_line_number_not_content(self):
        code, out, err = run_main(
            self.base_argv + ["--dotenv", self.env_file(f'ANTHROPIC_API_KEY="{SECRET}\n')])
        self.assertEqual(code, 1)
        self.assertIn("line 1", err)
        self.assertNotIn(SECRET, err)

    def test_base_url_set_refuses_naming_it(self):
        code, out, err = run_main(
            self.base_argv + ["--dotenv", self.env_file(f"ANTHROPIC_API_KEY={SECRET}\n")],
            env={"ANTHROPIC_BASE_URL": "https://gw.example"})
        self.assertEqual(code, 1)
        self.assertIn("ANTHROPIC_BASE_URL", err)
        self.assertNotIn(SECRET, err)

    def test_nothing_loadable_and_nothing_set_exits_1_naming_accepted_vars(self):
        code, out, err = run_main(self.base_argv + ["--dotenv", self.env_file("OTHER=1\n")])
        self.assertEqual(code, 1)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", err)

    def test_existing_env_value_is_kept_not_overridden(self):
        seen = []

        def fake(**kw):
            seen.append(kw["extra_env"])
            return result([row(1, 1, query="q1"), row(0, 1, False, query="q2")])

        code, out, err = run_main(
            self.base_argv + ["--dotenv", self.env_file(f"ANTHROPIC_API_KEY={SECRET}\n"
                                                         "CLAUDE_CODE_OAUTH_TOKEN=tok\n")],
            fake, env={"ANTHROPIC_API_KEY": "from-shell"})
        self.assertEqual(seen, [{"CLAUDE_CODE_OAUTH_TOKEN": "tok"}])
        self.assertIn("loaded CLAUDE_CODE_OAUTH_TOKEN; kept existing ANTHROPIC_API_KEY; "
                      "eval children see ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN", err)
        self.assertIn("2 credentials present", err)
        self.assertNotIn("from-shell", err + out)

    def test_dotenv_credential_suppresses_unisolated_warning(self):
        def fake(**kw):
            return result([row(1, 1, query="q1"), row(0, 1, False, query="q2")])
        code, out, err = run_main(
            self.base_argv + ["--dotenv", self.env_file("ANTHROPIC_API_KEY=k\n")], fake)
        self.assertNotIn("no credential in", err)


class ImproveGuardTest(unittest.TestCase):
    def test_compare_mode_results_exit_1_with_clear_message(self):
        import scripts.improve_description as imp
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            skill = make_skill(t)
            rj = t / "r.json"
            rj.write_text(json.dumps({"mode": "compare", "baseline": {}, "candidate": {},
                                      "comparison": {}}))
            err = io.StringIO()
            with mock.patch.object(sys, "argv", ["imp", "--eval-results", str(rj),
                                                 "--skill-path", str(skill), "--model", "x"]), \
                    contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    imp.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("compare", err.getvalue())
        self.assertNotIn("KeyError", err.getvalue())


if __name__ == "__main__":
    unittest.main()
