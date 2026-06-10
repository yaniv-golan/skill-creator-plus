import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from aggregate_benchmark import generate_benchmark, load_run_results  # noqa: E402


def make_grading(passed: int, failed: int, time_s: float = 10.0,
                 tokens: int | None = None, output_chars: int | None = None) -> dict:
    total = passed + failed
    g = {
        "expectations": [
            {"text": f"exp-{i}", "passed": i < passed, "evidence": "e"}
            for i in range(total)
        ],
        "summary": {
            "passed": passed, "failed": failed, "total": total,
            "pass_rate": round(passed / total, 4) if total else 0.0,
        },
        "timing": {"total_duration_seconds": time_s},
    }
    if tokens is not None:
        g["timing"]["total_tokens"] = tokens
    if output_chars is not None:
        g["execution_metrics"] = {"total_tool_calls": 3, "errors_encountered": 0,
                                  "output_chars": output_chars}
    return g


def write_eval(bench_dir: Path, eval_name: str, gradings: dict[str, dict],
               timing_json: dict[str, dict] | None = None) -> None:
    """gradings: config_name -> grading dict. timing_json: config_name -> timing.json dict."""
    for config, grading in gradings.items():
        cfg_dir = bench_dir / eval_name / config
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "grading.json").write_text(json.dumps(grading))
        if timing_json and config in timing_json:
            (cfg_dir / "timing.json").write_text(json.dumps(timing_json[config]))


class RunsArrayTest(unittest.TestCase):
    """Regression for the 0.4.1 variable-shadowing bug: the runs_per_configuration
    loop reused the name `runs`, so benchmark.json's runs array was replaced by
    the last config's raw result list."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bench = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_runs_array_has_all_configs_and_nested_result(self):
        write_eval(self.bench, "eval-1", {
            "with_skill": make_grading(4, 1),
            "without_skill": make_grading(2, 3),
        })
        benchmark = generate_benchmark(self.bench)
        runs = benchmark["runs"]
        self.assertEqual(len(runs), 2)
        configs = {r["configuration"] for r in runs}
        self.assertEqual(configs, {"with_skill", "without_skill"})
        for r in runs:
            self.assertIn("result", r)
            self.assertIn("pass_rate", r["result"])
        self.assertEqual(benchmark["metadata"]["runs_per_configuration"], 1)

    def test_non_eval_dir_without_hyphen_does_not_crash(self):
        # A stray directory like "logs" used to raise IndexError in
        # int(eval_dir.name.split("-")[1]).
        (self.bench / "logs").mkdir()
        write_eval(self.bench, "eval-1", {"with_skill": make_grading(1, 0)})
        benchmark = generate_benchmark(self.bench)  # must not raise
        self.assertEqual(len(benchmark["runs"]), 1)


if __name__ == "__main__":
    unittest.main()
