#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude to trigger (read the skill)
for a set of queries. Outputs results as JSON.
"""

import argparse
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.utils import parse_skill_md


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    model: str | None = None,
) -> dict:
    """Run a single query in an ISOLATED throwaway project root.

    Each run gets its own temp directory containing .claude/commands/<file>,
    so parallel workers can't see each other's (identically-described)
    command files — with a shared project root, a session that triggered a
    sibling worker's copy was scored as "did not trigger", systematically
    biasing rates at high concurrency.

    Returns {"triggered": bool, "error": str | None}. An error means the run
    produced no signal (CLI missing, crash before any stream event, timeout
    with no output) and must not be scored as a non-trigger.
    """
    unique_id = uuid.uuid4().hex[:8]
    clean_name = f"{skill_name}-skill-{unique_id}"

    with tempfile.TemporaryDirectory(prefix="skill-trigger-eval-") as tmp_root:
        project_commands_dir = Path(tmp_root) / ".claude" / "commands"
        command_file = project_commands_dir / f"{clean_name}.md"

        project_commands_dir.mkdir(parents=True, exist_ok=True)
        # Use YAML block scalar to avoid breaking on quotes in description
        indented_desc = "\n  ".join(skill_description.split("\n"))
        command_content = (
            f"---\n"
            f"description: |\n"
            f"  {indented_desc}\n"
            f"---\n\n"
            f"# {skill_name}\n\n"
            f"This skill handles: {skill_description}\n"
        )
        command_file.write_text(command_content)

        cmd = [
            "claude",
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session. The guard is for interactive terminal conflicts;
        # programmatic subprocess usage is safe.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=tmp_root,
                env=env,
            )
        except FileNotFoundError:
            return {"triggered": False, "error": "claude CLI not found on PATH"}

        triggered = False
        saw_event = False
        start_time = time.time()
        buffer = ""
        # Track state for stream event detection
        pending_tool_name = None
        accumulated_json = ""

        try:
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    remaining = process.stdout.read()
                    if remaining:
                        buffer += remaining.decode("utf-8", errors="replace")
                    break

                ready, _, _ = select.select([process.stdout], [], [], 1.0)
                if not ready:
                    continue

                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    saw_event = True

                    # Early detection via stream events
                    if event.get("type") == "stream_event":
                        se = event.get("event", {})
                        se_type = se.get("type", "")

                        if se_type == "content_block_start":
                            cb = se.get("content_block", {})
                            if cb.get("type") == "tool_use":
                                tool_name = cb.get("name", "")
                                if tool_name in ("Skill", "Read"):
                                    pending_tool_name = tool_name
                                    accumulated_json = ""
                                else:
                                    return {"triggered": False, "error": None}

                        elif se_type == "content_block_delta" and pending_tool_name:
                            delta = se.get("delta", {})
                            if delta.get("type") == "input_json_delta":
                                accumulated_json += delta.get("partial_json", "")
                                if clean_name in accumulated_json:
                                    return {"triggered": True, "error": None}

                        elif se_type in ("content_block_stop", "message_stop"):
                            if pending_tool_name:
                                return {"triggered": clean_name in accumulated_json, "error": None}
                            if se_type == "message_stop":
                                return {"triggered": False, "error": None}

                    # Fallback: full assistant message
                    elif event.get("type") == "assistant":
                        message = event.get("message", {})
                        for content_item in message.get("content", []):
                            if content_item.get("type") != "tool_use":
                                continue
                            tool_name = content_item.get("name", "")
                            tool_input = content_item.get("input", {})
                            if tool_name == "Skill" and clean_name in tool_input.get("skill", ""):
                                triggered = True
                            elif tool_name == "Read" and clean_name in tool_input.get("file_path", ""):
                                triggered = True
                            return {"triggered": triggered, "error": None}

                    elif event.get("type") == "result":
                        return {"triggered": triggered, "error": None}
        finally:
            # Clean up process on any exit path (return, exception, timeout)
            if process.poll() is None:
                process.kill()
                process.wait()

        # Fell out of the loop: process ended or timed out without a verdict.
        if not saw_event:
            rc = process.poll()
            if rc not in (0, None):
                return {"triggered": False,
                        "error": f"claude exited with code {rc} before any output"}
            return {"triggered": False,
                    "error": f"timeout after {timeout}s with no output from claude"}
        return {"triggered": triggered, "error": None}


def score_queries(
    eval_set: list[dict],
    query_runs: dict[str, list[dict]],
    trigger_threshold: float,
) -> tuple[list[dict], dict]:
    """Score per-query trigger results, excluding errored runs.

    Errored runs (CLI missing, crash, no-output timeout) carry no signal about
    the description, so they are excluded from the trigger-rate denominator
    instead of being counted as "did not trigger" — the old behavior inflated
    pass rates for should-NOT-trigger queries and deflated them for
    should-trigger queries whenever the environment hiccuped.
    """
    results = []
    errored_runs = 0
    total_runs = 0
    for item in eval_set:
        runs = query_runs.get(item["query"], [])
        ok = [r for r in runs if not r.get("error")]
        errs = [r for r in runs if r.get("error")]
        errored_runs += len(errs)
        total_runs += len(runs)
        triggers = sum(1 for r in ok if r["triggered"])
        if ok:
            trigger_rate = triggers / len(ok)
            if item["should_trigger"]:
                did_pass = trigger_rate >= trigger_threshold
            else:
                did_pass = trigger_rate < trigger_threshold
        else:
            trigger_rate = 0.0
            did_pass = False  # no usable signal — never a fabricated pass
        results.append({
            "query": item["query"],
            "should_trigger": item["should_trigger"],
            "trigger_rate": trigger_rate,
            "triggers": triggers,
            "runs": len(ok),
            "errors": len(errs),
            "error_messages": sorted({r["error"] for r in errs}),
            "pass": did_pass,
        })
    passed = sum(1 for r in results if r["pass"])
    return results, {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "errored_runs": errored_runs,
        "total_runs": total_runs,
    }


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
) -> dict:
    """Run the full eval set and return results."""
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    model,
                )
                future_to_info[future] = (item, run_idx)

        query_runs: dict[str, list[dict]] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            try:
                outcome = future.result()
            except Exception as e:
                outcome = {"triggered": False, "error": f"worker crashed: {e}"}
            if outcome.get("error"):
                print(f"Warning: run errored for query {query[:60]!r}: {outcome['error']}",
                      file=sys.stderr)
            query_runs.setdefault(query, []).append(outcome)

    results, summary = score_queries(eval_set, query_runs, trigger_threshold)
    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": summary,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run trigger evaluation for a skill description",
        epilog=(
            "Example:\n"
            "  python -m scripts.run_eval \\\n"
            "    --eval-set trigger-eval.json \\\n"
            "    --skill-path ./my-skill \\\n"
            "    --model claude-opus-4-7\n"
            "\n"
            "Output: JSON results to stdout. Requires the `claude` CLI on PATH.\n"
            "\n"
            "Exit codes:\n"
            "  0  evaluation completed (regardless of pass rate)\n"
            "  1  eval-set unreadable, skill not found, or every run errored"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use for claude -p (default: user's configured model)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))

    summary = output["summary"]
    if summary["errored_runs"]:
        print(
            f"Warning: {summary['errored_runs']}/{summary['total_runs']} runs errored "
            f"and were excluded from trigger rates.",
            file=sys.stderr,
        )
        if summary["errored_runs"] == summary["total_runs"]:
            print("Error: every run errored — no usable results. "
                  "Is the `claude` CLI installed and on PATH?", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
