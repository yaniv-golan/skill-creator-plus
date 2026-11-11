#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude to trigger (read the skill)
for a set of queries. Outputs results as JSON.
"""

import argparse
import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from scripts.utils import DotenvError, load_credentials_from_dotenv, parse_skill_md
except ImportError:
    sys.exit(
        "Error: this script uses package imports and must be run as a module "
        "from the skill directory:\n"
        "  cd <skill-creator-plus skill dir> && python -m scripts.run_eval ..."
    )


# Credential env vars that let a subprocess authenticate WITHOUT the operator's ~/.claude.
# Isolation is only possible when one is present: a fresh HOME has no credentials file, and the
# CLI answers "Not logged in" (verified).
CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN")

# A query no plausible description can miss. Its only job is to prove the DETECTOR is alive: if
# the synthesized command does not trigger on this, the run measured nothing and every "did not
# trigger" in the same batch is meaningless rather than informative.
CANARY_QUERY = "Use the {name} command right now. Invoke it immediately, without asking."


# The only names --dotenv will load. ANTHROPIC_AUTH_TOKEN is deliberately absent: it belongs with
# ANTHROPIC_BASE_URL (a gateway), and mixing a file's credential with the shell's base URL is how
# a key reaches the wrong host.
DOTENV_NAMES = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def isolation_available(extra_env: dict | None = None) -> bool:
    """True when a subprocess can authenticate without the operator's ~/.claude.

    `extra_env` (values loaded from --dotenv, never put into os.environ) counts the same as the
    environment: the child sees both.
    """
    return any(os.environ.get(v) or (extra_env or {}).get(v) for v in CREDENTIAL_ENV_VARS)


def credential_names_present(extra_env: dict | None = None) -> list[str]:
    """Names (never values) of the credential variables set for this run.

    Reads os.environ; `extra_env` is a hook for values supplied some other way, which win over
    the environment the same way they would for the child.
    """
    merged = {**os.environ, **(extra_env or {})}
    return [v for v in CREDENTIAL_ENV_VARS if merged.get(v)]


def installed_skill_names() -> set[str]:
    """Skill/plugin directory names discoverable from the operator's ~/.claude.

    Only used to explain a collision when isolation is unavailable. Best-effort: a name we miss
    costs a clearer error message, never a wrong score.
    """
    names: set[str] = set()
    home = Path(os.path.expanduser("~")) / ".claude"
    for pat in ("plugins/cache/*/*/*/skills/*", "skills/*"):
        for d in home.glob(pat):
            if d.is_dir():
                names.add(d.name)
    return names


def _subprocess_env(isolated_home: str | None, extra_env: dict | None = None) -> dict:
    """Env for a `claude -p` child.

    Removes CLAUDECODE (the guard is for interactive terminal conflicts; programmatic subprocess
    use is safe) and, when isolating, repoints HOME so the operator's installed plugins and skills
    are not discoverable. Without that, `claude -p` sees them and the model reaches for the REAL
    skill of the same name instead of the synthesized copy under test — the detector then scores a
    correct non-trigger and the whole eval reads as a bad description.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    # Merged into the CHILD's copy only; os.environ is never touched.
    env.update(extra_env or {})
    if isolated_home:
        env["HOME"] = isolated_home
    return env



def _invoked_skill_name(raw_json: str) -> str | None:
    """Best-effort skill name out of a (possibly truncated) tool-input JSON fragment."""
    try:
        v = json.loads(raw_json).get("skill")
        if isinstance(v, str) and v:
            return v
    except (ValueError, AttributeError):
        pass
    m = re.search(r'"skill"\s*:\s*"([^"]+)"', raw_json)
    return m.group(1) if m else None


def classify_invocation(invoked: str | None, clean_name: str, installed: frozenset) -> str:
    """'triggered' | 'hijacked' | 'other' for one Skill invocation.

    Called from BOTH the stream-event and the assistant return paths. The first version of this
    fix lived only in the assistant branch, which `--include-partial-messages` means is almost
    never reached — so hijacks were scored as plain non-triggers, i.e. the original bug, on the
    primary path. One function, two call sites, so they cannot drift apart again.

    'hijacked' is decided by membership in the operator's INSTALLED skills, not by a substring of
    the name under test. Substring is wrong in both directions: it misses a hijack to a SHORTER
    installed name (`skill-creator` while testing `skill-creator-plus` — both installed here), and
    it fires on any installed name containing a generic one like `docs`, `test` or `eval`, where a
    single false hit discards the whole run's scores.
    """
    if not invoked:
        return "other"
    if clean_name in invoked:
        return "triggered"
    # a plugin-qualified id is `plugin:skill`; compare the last segment too
    if invoked in installed or invoked.rsplit(":", 1)[-1] in installed:
        return "hijacked"
    return "other"


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    model: str | None = None,
    isolated_home: str | None = None,
    installed: frozenset = frozenset(),
    extra_env: dict | None = None,
) -> dict:
    """Run a single query in an ISOLATED throwaway project root.

    Each run gets its own temp directory containing .claude/commands/<file>,
    so parallel workers can't see each other's (identically-described)
    command files — with a shared project root, a session that triggered a
    sibling worker's copy was scored as "did not trigger", systematically
    biasing rates at high concurrency.

    Returns {"triggered": bool, "error": str | None}. An error means the run
    produced no signal (CLI missing, crash, an API error, a timeout before any
    answer text) and must not be scored as a non-trigger. API errors also carry
    `api_status` / `api_error` so callers can tell a rejected credential apart.
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

        env = _subprocess_env(isolated_home, extra_env)

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

        st = _StreamState()
        rc = None
        was_killed = False
        start_time = time.time()
        buffer = ""

        try:
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    # Self-exit: the final lines (the `assistant` error and the `is_error` result
                    # of a 401) are in this tail. It is parsed below like any other line.
                    remaining = process.stdout.read()
                    if remaining:
                        buffer += remaining.decode("utf-8", errors="replace")
                    break

                ready, _, _ = select.select([process.stdout], [], [], 1.0)
                if not ready:
                    continue

                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    # EOF usually means the child is exiting; give it a moment to say with what
                    # code, or a clean failure exit is mistaken for a kill.
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                verdict, buffer = _consume_lines(buffer, st, clean_name, installed)
                if verdict:
                    return verdict

            # Whatever is left (the drained tail, a final unterminated line) gets the same
            # handling as streamed lines; previously it was read and dropped.
            verdict, buffer = _consume_lines(buffer, st, clean_name, installed, final=True)
            if verdict:
                return verdict
        finally:
            # Clean up process on any exit path (return, exception, timeout)
            rc = process.poll()
            if rc is None:
                was_killed = True
                process.kill()
                process.wait()

        # Fell out of the loop: process ended or timed out without a verdict.
        return _end_of_run(st, rc, was_killed, timeout)


class _StreamState:
    """What the stream has shown so far, for events and for the end-of-run decision."""

    def __init__(self):
        self.saw_event = False
        # The most recent of: a `system` event, a `system/api_retry`, a thinking block start, a
        # text block start. Decides what a run that ends WITHOUT a verdict event means.
        self.last_kind = "none"  # none | system | retry | thinking | text
        self.last_retry: dict | None = None
        self.pending_tool_name: str | None = None
        self.accumulated_json = ""


def _api_error_text(status, text=None, code=None) -> str:
    """`api error <status>: <text>`, or `api error (<code>)` when the status is null.

    Connection failures report `error_status: null, error: "unknown"` and "Not logged in" reports
    `api_error_status: null`; formatting those with the status would print "None".
    """
    if status is not None:
        return f"api error {status}" + (f": {text}" if text else "")
    return f"api error ({code or text or 'unknown'})"


def _api_error(status, text=None, code=None, suffix="") -> dict:
    return {"triggered": False, "hijacked_by": None, "api_status": status, "api_error": code,
            "error": _api_error_text(status, text, code) + suffix}


def _errored(message: str) -> dict:
    return {"triggered": False, "error": message, "hijacked_by": None}


def _message_text(message: dict) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return ""
    return " ".join(c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text").strip()


def _consume_lines(buffer: str, st: "_StreamState", clean_name: str, installed,
                   final: bool = False):
    """Parse every complete line in `buffer` (and, if `final`, a trailing unterminated one).

    Returns (verdict-or-None, unconsumed rest). One path for streamed lines, the post-exit tail
    and a last partial line, so they cannot drift apart.
    """
    lines = buffer.split("\n")
    rest = lines.pop()  # "" when the buffer ended on a newline
    if final and rest.strip():
        lines.append(rest)
        rest = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        verdict = _handle_event(event, st, clean_name, installed)
        if verdict:
            return verdict, rest
    return None, rest


def _handle_event(event, st: "_StreamState", clean_name: str, installed) -> dict | None:
    """Update `st` from one stream-json event; return a result dict if it decides the run."""
    if not isinstance(event, dict):
        return None
    st.saw_event = True
    etype = event.get("type")

    if etype == "system":
        if event.get("subtype") == "api_retry":
            st.last_kind = "retry"
            st.last_retry = event
        elif st.last_kind == "none":
            # Only a system event BEFORE any model output says "nothing has happened yet". After
            # thinking or answer text has started, a status/hook event is bookkeeping, not a
            # stall: letting it overwrite last_kind would turn a long text-only answer that runs
            # past --timeout (a legitimate non-trigger, row 5) into an errored run (row 4).
            st.last_kind = "system"

    # Early detection via stream events
    elif etype == "stream_event":
        se = event.get("event", {})
        se_type = se.get("type", "")

        if se_type == "content_block_start":
            cb = se.get("content_block", {})
            if cb.get("type") == "tool_use":
                tool_name = cb.get("name", "")
                if tool_name in ("Skill", "Read"):
                    st.pending_tool_name = tool_name
                    st.accumulated_json = ""
                else:
                    return {"triggered": False, "error": None}
            elif cb.get("type") == "thinking":
                st.last_kind = "thinking"
            elif cb.get("type") == "text":
                st.last_kind = "text"

        elif se_type == "content_block_delta" and st.pending_tool_name:
            delta = se.get("delta", {})
            if delta.get("type") == "input_json_delta":
                st.accumulated_json += delta.get("partial_json", "")
                if clean_name in st.accumulated_json:
                    return {"triggered": True, "error": None, "hijacked_by": None}

        elif se_type in ("content_block_stop", "message_stop"):
            if st.pending_tool_name:
                invoked = _invoked_skill_name(st.accumulated_json)
                verdict = classify_invocation(invoked, clean_name, installed)
                return {
                    "triggered": verdict == "triggered",
                    "error": None,
                    "hijacked_by": invoked if verdict == "hijacked" else None,
                }
            if se_type == "message_stop":
                return {"triggered": False, "error": None, "hijacked_by": None}

    # Fallback: full assistant message
    elif etype == "assistant":
        # A non-null top-level `error` is the CLI reporting a failed API call (a 401 arrives this
        # way, with no stream events at all). Checked before anything else: the synthetic message
        # that carries it is not model output.
        if event.get("error") is not None:
            message = event.get("message", {})
            return _api_error(event.get("api_error_status"), _message_text(message),
                              event["error"])
        message = event.get("message", {})
        if message.get("model") == "<synthetic>":
            return None
        for content_item in message.get("content", []):
            if content_item.get("type") != "tool_use":
                continue
            tool_name = content_item.get("name", "")
            tool_input = content_item.get("input", {})
            invoked = tool_input.get("skill", "")
            verdict = (classify_invocation(invoked, clean_name, installed)
                       if tool_name == "Skill" else "other")
            triggered = False
            hijacked_by = None
            if verdict == "triggered":
                triggered = True
            elif verdict == "hijacked":
                # The model reached for a DIFFERENT skill whose name contains the
                # one under test — i.e. the operator's INSTALLED copy, visible
                # because HOME was not isolated. Scoring this as "did not trigger"
                # is technically true and completely misleading: the description
                # worked, it just routed to the wrong instance. Record it so the
                # run can say "not measured" instead of "scored badly".
                hijacked_by = invoked
            elif tool_name == "Read" and clean_name in tool_input.get("file_path", ""):
                triggered = True
            return {"triggered": triggered, "error": None, "hijacked_by": hijacked_by}

    elif etype == "result":
        # Gate on `is_error`, not `subtype`: a 401 arrives as subtype "success".
        if event.get("is_error"):
            return _api_error(event.get("api_error_status"), event.get("result"))
        return {"triggered": False, "error": None, "hijacked_by": None}

    return None


def _end_of_run(st: "_StreamState", rc, was_killed: bool, timeout: int) -> dict:
    """Decide a run that ended with no verdict event. First match wins.

    Only one outcome is clean: a timeout while the model was streaming answer text (row 5), since
    a should-not-trigger query answered at length can legitimately outlast --timeout. Anything
    else carries no signal about the description and must not be scored as a non-trigger.
    """
    # 1. A Skill/Read call was mid-flight: the verdict was lost with the stream.
    if st.pending_tool_name:
        return _errored("stream ended mid tool call")
    retry = st.last_retry
    # 2. The child failed on its own.
    if not was_killed and rc not in (0, None):
        msg = f"claude exited with code {rc}" + ("" if st.saw_event else " before any output")
        if retry:
            msg += " (last " + _api_error_text(retry.get("error_status"), retry.get("error"),
                                               retry.get("error")) + ")"
        return _errored(msg)
    # 3. The CLI was still retrying a failing API call when the run ended (last event wins, so
    #    retry -> text -> timeout is row 5, but text -> retry -> timeout is here).
    if st.last_kind == "retry":
        return _api_error(
            retry.get("error_status"), retry.get("error"), retry.get("error"),
            f" (claude was still retrying, attempt {retry.get('attempt')}/"
            f"{retry.get('max_retries')})")
    # 4. No answer text yet. Thinking included: no answer ends on thinking, so a timeout there
    #    is undecided and could be hiding a real trigger.
    if st.last_kind in ("none", "system", "thinking"):
        if not was_killed:
            return _errored("claude exited before answer text")
        if st.last_kind == "none":
            return _errored(f"timeout after {timeout}s with no output from claude")
        if st.last_kind == "thinking":
            return _errored(f"timeout after {timeout}s mid-thinking")
        return _errored(f"timeout after {timeout}s before answer text")
    # 5. Killed by the timeout while streaming answer text.
    if was_killed:
        return {"triggered": False, "error": None, "hijacked_by": None}
    # 6. Exited 0 after answer text but without message_stop or a result.
    return _errored("claude exited without a result")


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
    extra_env: dict | None = None,
) -> dict:
    """Run the full eval set and return results.

    Raises InstrumentError when the canary fails — see `run_canary`.
    """
    with tempfile.TemporaryDirectory(prefix="skill-eval-home-") as home_dir:
        isolated_home = home_dir if isolation_available(extra_env) else None
        # The unisolated warning is the CALLER's job (main / run_loop.main), so it prints once per
        # invocation rather than once per run_eval() call, i.e. once per loop iteration.
        return _run_eval_inner(
            eval_set, skill_name, description, num_workers, timeout,
            runs_per_query, trigger_threshold, model, isolated_home, extra_env,
        )


def _warn_unisolated(skill_name: str) -> None:
    """Explain the one condition under which this eval silently measures nothing."""
    collides = skill_name in installed_skill_names()
    print(
        f"Warning: no credential in {'/'.join(CREDENTIAL_ENV_VARS)}, so this eval runs against "
        f"your real ~/.claude and every installed skill is visible to the model.",
        file=sys.stderr,
    )
    if collides:
        print(
            f"  '{skill_name}' IS INSTALLED on this machine, so a query MAY invoke the real skill "
            f"instead of the copy under test. That is intermittent, not certain — when it happens "
            f"the run is detected and refused rather than scored. Export a credential to isolate.",
            file=sys.stderr,
        )


def run_canary(skill_name, description, timeout, model, isolated_home, installed,
               extra_env=None) -> dict:
    """Prove the detector can fire at all before believing any 'did not trigger'.

    A dead detector and a bad description are indistinguishable in a score: both are low numbers
    with no errors. This was not hypothetical — an eval of this very skill reported 8/24 with all
    16 positives failing, including a query the description names almost verbatim, because the
    model kept reaching for the INSTALLED skill of the same name. The run looked like a description
    problem and was an instrument problem.
    """
    return run_single_query(
        CANARY_QUERY.format(name=f"{skill_name}-skill"),
        skill_name, description, timeout, model, isolated_home, installed, extra_env,
    )


class InstrumentError(RuntimeError):
    """The eval could not measure anything — scores would be noise, so none are reported."""


def _run_eval_inner(
    eval_set, skill_name, description, num_workers, timeout,
    runs_per_query, trigger_threshold, model, isolated_home, extra_env=None,
) -> dict:
    installed = frozenset(installed_skill_names())
    canary = run_canary(skill_name, description, timeout, model, isolated_home, installed,
                        extra_env)
    if canary.get("error") and (canary.get("api_status") in (401, 403)
                                or canary.get("api_error") == "authentication_failed"):
        # The credential is the first suspect ONLY for an auth rejection. Any other canary error
        # (CLI missing, a connection failure, a crash) says nothing about it and keeps the
        # neutral CANARY FAILED text below.
        names = credential_names_present(extra_env)
        raise InstrumentError(
            f"CANARY ERRORED: {canary['error']}\n"
            "  the API rejected the request's authentication, so nothing was measured.\n"
            + (f"  credential(s) in the environment (names only): {', '.join(names)}. "
               "Check that it is valid and not expired."
               if names else
               f"  none of {'/'.join(CREDENTIAL_ENV_VARS)} is set, so the CLI used whatever "
               "login ~/.claude holds. Export a credential, or log in with `claude /login`.")
        )
    if not canary.get("triggered"):
        raise InstrumentError(
            "CANARY FAILED — the synthesized command did not trigger on a query that names it "
            "outright, so this eval cannot detect a trigger and every score would be noise.\n"
            f"  canary error: {canary.get('error') or 'none (ran clean, simply did not trigger)'}\n"
            + (f"  the canary was HIJACKED to {canary['hijacked_by']!r} — an installed skill "
               f"answered instead of the copy under test. That is the cause, not a guess.\n"
               if canary.get("hijacked_by") else "")
            + (
                "  HOME was isolated, so an installed skill of the same name is not the cause; "
                "suspect the CLI, the model, or the detector itself."
                if isolated_home else
                "  HOME was NOT isolated (no credential in the environment), so the likeliest "
                "cause is the model reaching for an installed skill instead of the copy under "
                f"test. Export one of {'/'.join(CREDENTIAL_ENV_VARS)} and re-run."
            )
        )

    hijacked: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
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
                    isolated_home,
                    installed,
                    extra_env,
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
            if outcome.get("hijacked_by"):
                hijacked.append((query, outcome["hijacked_by"]))
            query_runs.setdefault(query, []).append(outcome)

    if hijacked:
        # Not a low score — an unmeasured run. The description did its job and the invocation
        # went to the operator's INSTALLED copy of the same skill, which the detector can only
        # score as a non-trigger. Refusing is the point: this is the exact failure that made an
        # earlier eval of this skill report 8/24 and read as a description problem.
        sample = "\n".join(f"    {q[:60]!r} -> invoked {n!r}" for q, n in hijacked[:3])
        raise InstrumentError(
            f"HIJACKED — {len(hijacked)} run(s) invoked an INSTALLED skill instead of the copy "
            f"under test, so those queries were not measured:\n{sample}\n"
            f"  Export one of {'/'.join(CREDENTIAL_ENV_VARS)} to isolate HOME and re-run."
        )

    results, summary = score_queries(eval_set, query_runs, trigger_threshold)
    return {
        "skill_name": skill_name,
        "description": description,
        # Provenance of the measurement, not decoration. `isolated: false` means the operator's
        # installed skills were visible to the model and a hijack was possible; `canary` proves the
        # detector could fire at all. Both ride in the artifact rather than only on stderr, so a
        # refactor that drops isolation is visible in every result a user ever looks at — not only
        # when someone has written the right mock in CI.
        "isolated": bool(isolated_home),
        "canary": {"triggered": canary.get("triggered"),
                   "hijacked_by": canary.get("hijacked_by")},
        "results": results,
        "summary": summary,
    }


def warn_slash_queries(eval_set) -> None:
    """Warn (not fail) about queries the CLI will handle itself.

    `/cost`, `/help` and the like are slash commands run by the CLI without asking the model, so
    such a query cannot trigger anything and would read as a description failure.
    """
    for item in eval_set if isinstance(eval_set, list) else []:
        q = item.get("query") if isinstance(item, dict) else None
        if isinstance(q, str) and q.lstrip().startswith("/"):
            print(f"Warning: query starts with '/': {q[:60]!r}. The CLI treats it as a slash "
                  f"command and never asks the model, so it cannot trigger.", file=sys.stderr)


def find_duplicate_queries(eval_set) -> list[str]:
    """Query texts that appear more than once, in first-seen order.

    Runs are keyed by query text, so duplicates would pool their runs into one row, and
    run_loop's train/test split also works by text. Rejected everywhere rather than half-handled.
    """
    seen: set[str] = set()
    dups: list[str] = []
    for item in eval_set if isinstance(eval_set, list) else []:
        q = item.get("query") if isinstance(item, dict) else None
        if not isinstance(q, str):
            continue
        if q in seen and q not in dups:
            dups.append(q)
        seen.add(q)
    return dups


def reject_duplicate_queries(eval_set) -> None:
    dups = find_duplicate_queries(eval_set)
    if dups:
        shown = "\n".join(f"  {q[:80]!r}" for q in dups[:10])
        print(f"Error: {len(dups)} duplicate query text(s) in the eval set (runs are keyed by "
              f"query text, so duplicates would pool):\n{shown}", file=sys.stderr)
        sys.exit(1)


def load_dotenv_extra_env(path: str, only: str | None = None) -> dict:
    """Resolve --dotenv into an `extra_env` for the eval children. Exits 1 on any refusal.

    `only` (--dotenv-key) restricts loading to one name. It exists because a file holding BOTH
    credentials hands both to the children, and the `claude` CLI then prefers the API key: a stale
    key in a shared .env made every run 401 while a valid OAuth token sat beside it (measured).

    Never mutates os.environ: the returned values go only to the `claude -p` children. Shared by
    run_eval.main and run_loop.main so both apply identical rules. Messages carry names and line
    numbers only, never a value.
    """
    if os.environ.get("ANTHROPIC_BASE_URL"):
        print("Error: --dotenv refused: ANTHROPIC_BASE_URL is set in the environment. A file's "
              "credential combined with a shell's base URL can send a key to the wrong host. "
              "Export the credential yourself for gateway setups.", file=sys.stderr)
        sys.exit(1)
    if only is not None and only not in DOTENV_NAMES:
        print(f"Error: --dotenv-key must be one of {', '.join(DOTENV_NAMES)}.", file=sys.stderr)
        sys.exit(1)
    names = (only,) if only else DOTENV_NAMES
    try:
        found = load_credentials_from_dotenv(path, names)
    except DotenvError as e:
        print(f"Error: --dotenv: {e}", file=sys.stderr)
        sys.exit(1)
    kept = [n for n in DOTENV_NAMES if os.environ.get(n)]
    # A name already set in the environment wins and is not copied into extra_env.
    extra = {n: v for n, v in found.items() if n not in kept}
    if not extra and not any(os.environ.get(v) for v in CREDENTIAL_ENV_VARS):
        print(f"Error: --dotenv: no {' or '.join(names)} found in the file, and none is "
              f"set in the environment.", file=sys.stderr)
        sys.exit(1)
    seen = [n for n in DOTENV_NAMES if n in extra or n in kept]
    line = (f"dotenv: loaded {', '.join(extra) or 'none'}; kept existing "
            f"{', '.join(kept) or 'none'}; eval children see {', '.join(seen) or 'none'}")
    if len(seen) == 2:
        line += " (2 credentials present; the claude CLI's precedence picks one)"
    print(line, file=sys.stderr)
    return extra


def _change_for(a_usable: int, b_usable: int, a: int, b: int, a_pass: bool, b_pass: bool) -> str:
    if a_usable == 0 or b_usable == 0:
        return "errored"
    if a_pass == b_pass:
        return "same"
    d = abs(a - b)
    # Integer arithmetic on purpose: as a float rate difference 2 -> 7 of 10 is 0.49999... and
    # would be misread as under half.
    if a_usable != b_usable or 2 * d < a_usable or d < 2:
        return "within_noise"
    return "fixed" if b_pass else "regressed"


def compare_results(baseline: dict, candidate: dict) -> dict:
    """Pair two run_eval() results row by row (by position; both arms iterate the same eval set).

    `change`, first match wins: errored (an arm has no usable run) -> same (no pass flip) ->
    within_noise (usable counts differ, or the swing is under half of n, or under 2 runs) ->
    fixed / regressed.
    """
    rows = []
    counts = {"fixed": 0, "regressed": 0, "within_noise": 0, "same": 0, "errored": 0}
    for b, c in zip(baseline["results"], candidate["results"]):
        change = _change_for(b["runs"], c["runs"], b["triggers"], c["triggers"],
                             b["pass"], c["pass"])
        counts[change] += 1
        rows.append({
            "query": b["query"],
            "should_trigger": b["should_trigger"],
            "baseline_triggers": b["triggers"],
            "baseline_usable": b["runs"],
            "baseline_errors": b["errors"],
            "candidate_triggers": c["triggers"],
            "candidate_usable": c["runs"],
            "candidate_errors": c["errors"],
            "baseline_pass": b["pass"],
            "candidate_pass": c["pass"],
            "change": change,
        })
    return {
        "rows": rows,
        "summary": {
            **counts,
            "total": len(rows),
            "baseline_passed": sum(1 for r in rows if r["baseline_pass"]),
            "candidate_passed": sum(1 for r in rows if r["candidate_pass"]),
            "note": "baseline_passed / candidate_passed are raw counts and include within_noise flips",
        },
    }


_CHANGE_LABEL = {"fixed": "FIXED", "regressed": "REGRESSED", "within_noise": "within noise",
                 "same": "same", "errored": "errored"}


def _print_compare_rows(comparison: dict) -> None:
    for r in comparison["rows"]:
        print(f"  baseline {r['baseline_triggers']}/{r['baseline_usable']} \u2192 "
              f"candidate {r['candidate_triggers']}/{r['candidate_usable']}  "
              f"[{_CHANGE_LABEL[r['change']]}] expected={r['should_trigger']}: {r['query'][:70]}",
              file=sys.stderr)


def _every_run_errored(output: dict) -> bool:
    s = output["summary"]
    return bool(s["errored_runs"]) and s["errored_runs"] == s["total_runs"]


def main():
    parser = argparse.ArgumentParser(
        description="Run trigger evaluation for a skill description",
        epilog=(
            "Example:\n"
            "  python -m scripts.run_eval \\\n"
            "    --eval-set trigger-eval.json \\\n"
            "    --skill-path ./my-skill \\\n"
            "    --model <model-id>\n"
            "\n"
            "Use the model ID of the session whose triggering you want to match.\n"
            "\n"
            "Compare two descriptions in one command (baseline arm first, then candidate):\n"
            "  ... --baseline-description-file old.txt --description \"new text\"\n"
            "  The candidate is --description, or the SKILL.md description. Compare mode doubles\n"
            "  the cost. Per query, `change` is: errored (an arm has no usable run); same (the\n"
            "  pass/fail verdict did not flip); within_noise (the arms' usable run counts differ,\n"
            "  or the trigger counts differ by under half of the runs or by under 2); else\n"
            "  fixed / regressed. At --runs-per-query 1 every flip is within noise; use 5+ runs\n"
            "  when a decision rests on one query. The arms run one after the other, so time\n"
            "  drift (rate limits, error bursts) can differ between them.\n"
            "\n"
            "--dotenv PATH loads ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN for the eval\n"
            "children only (never into this process's environment); refused when\n"
            "ANTHROPIC_BASE_URL is set. If the file holds both, both reach the children and the\n"
            "CLI prefers the API key; --dotenv-key NAME loads only that one.\n"
            "\n"
            "Output: JSON results to stdout. Requires the `claude` CLI on PATH.\n"
            "\n"
            "Exit codes:\n"
            "  0  evaluation completed (regardless of pass rate)\n"
            "  1  eval-set unreadable or has duplicate queries, skill not found, --dotenv\n"
            "     refused, or every run errored (in either arm, in compare mode)\n"
            "  4  INSTRUMENT FAILURE — the canary did not trigger, or a run invoked an installed\n"
            "     copy of the skill instead of the one under test, so nothing was measured\n"
            "     and no scores are reported (distinct from a low score, which is a finding)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--baseline-description", default=None,
                          help="Compare mode: the baseline description text")
    baseline.add_argument("--baseline-description-file", default=None,
                          help="Compare mode: path to a file holding the baseline description")
    parser.add_argument("--dotenv", default=None,
                        help="Dotenv file to read ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN from (eval children only)")
    parser.add_argument("--dotenv-key", default=None, choices=DOTENV_NAMES,
                        help="With --dotenv: load only this credential from the file")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use for claude -p (default: user's configured model)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    # Before any other work: a refused dotenv must not leave side effects behind.
    if args.dotenv_key and not args.dotenv:
        parser.error("--dotenv-key needs --dotenv")
    extra_env = load_dotenv_extra_env(args.dotenv, args.dotenv_key) if args.dotenv else None

    eval_set = json.loads(Path(args.eval_set).read_text())
    warn_slash_queries(eval_set)
    reject_duplicate_queries(eval_set)
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description

    baseline_description = args.baseline_description
    if args.baseline_description_file is not None:
        try:
            baseline_description = Path(args.baseline_description_file).read_text().strip()
        except OSError as e:
            print(f"Error: cannot read --baseline-description-file: {type(e).__name__}",
                  file=sys.stderr)
            sys.exit(1)
    compare = baseline_description is not None

    if args.verbose:
        if compare:
            print(f"Baseline: {baseline_description}", file=sys.stderr)
            print(f"Candidate: {description}", file=sys.stderr)
        else:
            print(f"Evaluating: {description}", file=sys.stderr)

    if not isolation_available(extra_env):
        _warn_unisolated(name)  # once per invocation, whatever the mode

    def arm(desc):
        return run_eval(
            eval_set=eval_set,
            skill_name=name,
            description=desc,
            num_workers=args.num_workers,
            timeout=args.timeout,
            runs_per_query=args.runs_per_query,
            trigger_threshold=args.trigger_threshold,
            model=args.model,
            extra_env=extra_env,
        )

    if compare:
        _main_compare(arm, baseline_description, description, args)
        return

    try:
        output = arm(description)
    except InstrumentError as e:
        # Exit 4, distinct from 1: "this eval measured nothing" is a different fact from
        # "the description scored badly", and a caller that conflates them optimizes against
        # noise. run_loop.py relies on this code.
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(4)

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


def _main_compare(arm, baseline_description: str, description: str, args) -> None:
    """Baseline arm, then candidate arm, then the pairing. Exits 4 / 1 as the epilog says."""
    try:
        base = arm(baseline_description)
    except InstrumentError as e:
        # Stop here: the candidate arm would be paid for against the same dead instrument.
        print(f"Error: baseline: {e}", file=sys.stderr)
        sys.exit(4)
    try:
        cand = arm(description)
    except InstrumentError as e:
        # The baseline half was paid for; do not lose it.
        print(json.dumps({"mode": "compare", "baseline": base, "candidate": None,
                          "comparison": None}, indent=2))
        print(f"Error: candidate: {e}", file=sys.stderr)
        sys.exit(4)

    comparison = compare_results(base, cand)
    print(json.dumps({"mode": "compare", "baseline": base, "candidate": cand,
                      "comparison": comparison}, indent=2))

    s = comparison["summary"]
    if args.verbose:
        _print_compare_rows(comparison)
    print(f"Compare: {s['fixed']} fixed, {s['regressed']} regressed, {s['within_noise']} within "
          f"noise, {s['same']} same, {s['errored']} errored (baseline {s['baseline_passed']}/"
          f"{s['total']} passed, candidate {s['candidate_passed']}/{s['total']}; raw counts include "
          f"within-noise flips)", file=sys.stderr)

    exit_code = 0
    for label, out in (("baseline", base), ("candidate", cand)):
        es = out["summary"]
        if es["errored_runs"]:
            print(f"Warning: {label}: {es['errored_runs']}/{es['total_runs']} runs errored and "
                  f"were excluded from trigger rates.", file=sys.stderr)
            if _every_run_errored(out):
                print(f"Error: {label}: every run errored — no usable results. "
                      "Is the `claude` CLI installed and on PATH?", file=sys.stderr)
                exit_code = 1
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
