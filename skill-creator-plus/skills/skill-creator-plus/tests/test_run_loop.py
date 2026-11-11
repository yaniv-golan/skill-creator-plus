import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Insert the SKILL ROOT (parent of scripts/): run_loop.py does
# `from scripts...` imports, which need the package importable.
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
import scripts.improve_description as improve_mod  # noqa: E402
import scripts.run_loop as run_loop_mod  # noqa: E402
from scripts.run_eval import CREDENTIAL_ENV_VARS  # noqa: E402
from scripts.run_loop import split_eval_set  # noqa: E402

CLEAN_ENV = {v: "" for v in CREDENTIAL_ENV_VARS + ("ANTHROPIC_BASE_URL",)}
SECRET = "sk-ant-LOOPSECRET-9876543210"


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


class ResultsDirIsCreatedBeforeWriteTests(unittest.TestCase):
    """A non-existent --results-dir must not crash before the loop starts.

    Regression pin: the live report is written into the --results-dir anchor, but the directory
    is created later in main(). The old default (system temp) always existed, so nothing caught
    it when the default changed. Runs the CLI because the bug lives in main()'s ordering, not in
    an importable helper.
    """

    def test_nonexistent_results_dir_does_not_crash_at_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skill = tmp / "sk"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: sk\ndescription: d\n---\nB\n")
            eval_set = tmp / "es.json"
            eval_set.write_text('{"queries": []}')
            target = tmp / "does" / "not" / "exist"
            proc = subprocess.run(
                [sys.executable, "-m", "scripts.run_loop",
                 "--eval-set", str(eval_set), "--skill-path", str(skill),
                 "--model", "x", "--results-dir", str(target)],
                cwd=str(SKILL_ROOT), capture_output=True, text=True, timeout=120,
            )
            self.assertNotIn("FileNotFoundError", proc.stderr)
            self.assertTrue(target.exists(), "the anchor directory was not created before use")


def _skill_and_evals(tmp: Path):
    skill = tmp / "sk"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: sk\ndescription: d\n---\nB\n")
    es = tmp / "es.json"
    es.write_text(json.dumps([{"query": f"t{i}", "should_trigger": True} for i in range(3)] +
                             [{"query": f"n{i}", "should_trigger": False} for i in range(3)]))
    return skill, es


class DotenvLoopTests(unittest.TestCase):
    def test_stub_claude_sees_the_dotenv_credential_and_canary_exit_is_4(self):
        """Real subprocess chain: run_loop -> run_eval -> `claude` (a stub first on PATH)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skill, es = _skill_and_evals(tmp)
            bindir = tmp / "bin"
            bindir.mkdir()
            record = tmp / "child-env.txt"
            stub = bindir / "claude"
            # Non-triggering stream: message_stop with no tool call -> the canary does not fire.
            stub.write_text(
                "#!/bin/sh\n"
                f'printf "%s" "$ANTHROPIC_API_KEY" > "{record}"\n'
                'echo \'{"type":"stream_event","event":{"type":"message_stop"}}\'\n'
            )
            stub.chmod(0o755)
            dotenv = tmp / ".env"
            dotenv.write_text(f"ANTHROPIC_API_KEY={SECRET}\n")
            env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV}
            env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
            proc = subprocess.run(
                [sys.executable, "-m", "scripts.run_loop", "--eval-set", str(es),
                 "--skill-path", str(skill), "--model", "x", "--report", "none",
                 "--dotenv", str(dotenv)],
                cwd=str(SKILL_ROOT), capture_output=True, text=True, timeout=120, env=env)
            self.assertEqual(proc.returncode, 4, proc.stderr)
            self.assertEqual(record.read_text(), SECRET, "the stub child never saw the credential")
            self.assertNotIn(SECRET, proc.stdout + proc.stderr)
            self.assertEqual(proc.stderr.count("no credential in"), 0)

    def test_dotenv_value_is_not_in_the_improvers_env(self):
        passing = lambda fails: {  # noqa: E731
            "results": [{"query": q, "should_trigger": st, "trigger_rate": 0.0, "triggers": 0,
                         "runs": 1, "errors": 0, "error_messages": [], "pass": not fails}
                        for q, st in (("t0", True), ("t1", True), ("n0", False), ("n1", False))],
            "summary": {"total": 4, "passed": 0 if fails else 4, "failed": 4 if fails else 0,
                        "errored_runs": 0, "total_runs": 4}}
        results = [passing(True), passing(False)]
        eval_set = [{"query": "t0", "should_trigger": True}, {"query": "t1", "should_trigger": True},
                    {"query": "n0", "should_trigger": False}, {"query": "n1", "should_trigger": False}]
        seen_extra, improver_envs = [], []

        def fake_run_eval(**kw):
            seen_extra.append(kw["extra_env"])
            return results.pop(0)

        def fake_subprocess_run(cmd, **kw):
            improver_envs.append(kw["env"])
            return subprocess.CompletedProcess(cmd, 0, "<new_description>better</new_description>", "")

        with tempfile.TemporaryDirectory() as tmp:
            skill, _ = _skill_and_evals(Path(tmp))
            with mock.patch.dict(os.environ, CLEAN_ENV), \
                    mock.patch.object(run_loop_mod, "run_eval", fake_run_eval), \
                    mock.patch.object(improve_mod.subprocess, "run", fake_subprocess_run):
                before = dict(os.environ)
                run_loop_mod.run_loop(
                    eval_set=eval_set, skill_path=skill, description_override=None, num_workers=1,
                    timeout=1, max_iterations=3, runs_per_query=1, trigger_threshold=0.5,
                    holdout=0, model="x", verbose=False,
                    extra_env={"ANTHROPIC_API_KEY": SECRET})
                self.assertEqual(dict(os.environ), before)
        self.assertEqual(seen_extra, [{"ANTHROPIC_API_KEY": SECRET}] * 2)
        self.assertEqual(len(improver_envs), 1)
        self.assertEqual(improver_envs[0].get("ANTHROPIC_API_KEY", ""), "")  # hygiene patch: empty
        self.assertNotIn(SECRET, improver_envs[0].values())

    def test_bad_dotenv_exits_1_before_any_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skill, es = _skill_and_evals(tmp)
            report = tmp / "out" / "report.html"
            results_dir = tmp / "res"
            err = io.StringIO()
            argv = ["run_loop", "--eval-set", str(es), "--skill-path", str(skill), "--model", "x",
                    "--report", str(report), "--results-dir", str(results_dir),
                    "--dotenv", str(tmp / "missing.env")]
            with mock.patch.dict(os.environ, CLEAN_ENV), mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(run_loop_mod.webbrowser, "open") as opened, \
                    contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    run_loop_mod.main()
            self.assertEqual(cm.exception.code, 1)
            self.assertFalse(report.exists())
            self.assertFalse(report.parent.exists())
            self.assertFalse(results_dir.exists())
            opened.assert_not_called()

    def test_duplicate_queries_exit_1_naming_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skill, es = _skill_and_evals(tmp)
            es.write_text(json.dumps([{"query": "dup", "should_trigger": True},
                                      {"query": "dup", "should_trigger": False}]))
            err = io.StringIO()
            argv = ["run_loop", "--eval-set", str(es), "--skill-path", str(skill), "--model", "x",
                    "--report", "none"]
            with mock.patch.dict(os.environ, CLEAN_ENV), mock.patch.object(sys, "argv", argv), \
                    contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    run_loop_mod.main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("'dup'", err.getvalue())

    def test_unisolated_warning_prints_once_across_iterations(self):
        def failing(**kw):
            return {"results": [{"query": "t0", "should_trigger": True, "trigger_rate": 0.0,
                                 "triggers": 0, "runs": 1, "errors": 0, "error_messages": [],
                                 "pass": False}],
                    "summary": {"total": 1, "passed": 0, "failed": 1, "errored_runs": 0,
                                "total_runs": 1}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            skill, es = _skill_and_evals(tmp)
            es.write_text(json.dumps([{"query": "t0", "should_trigger": True}]))
            err, out = io.StringIO(), io.StringIO()
            argv = ["run_loop", "--eval-set", str(es), "--skill-path", str(skill), "--model", "x",
                    "--report", "none", "--holdout", "0", "--max-iterations", "3",
                    "--plateau-patience", "9"]
            with mock.patch.dict(os.environ, CLEAN_ENV), mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(run_loop_mod, "run_eval", failing), \
                    mock.patch.object(run_loop_mod, "improve_description", return_value="nd"), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                run_loop_mod.main()
            self.assertEqual(err.getvalue().count("no credential in"), 1)


if __name__ == "__main__":
    unittest.main()
