"""Exercise an immutable ZIP's deadlines, retries and CSV checkpoints on localhost.

Only synthetic data and a mock HTTP API are used. Passing this check does not
measure answer quality or predict the platform score. No runtime is patched.
"""
import argparse
from collections import Counter
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from zipfile import ZipFile


MARKER = re.compile(r"BUDGET_ROW_(\d{4})")
CASES = (
    {"name": "healthy_3", "rows": 3, "workers": 1, "budget": 2, "delay": .04, "mode": "healthy"},
    {"name": "deadline_30", "rows": 30, "workers": 1, "budget": 1, "delay": .20, "mode": "deadline"},
    {"name": "deadline_300", "rows": 300, "workers": 3, "budget": 2, "delay": .15, "mode": "deadline"},
    {"name": "recover_429_503", "rows": 3, "workers": 3, "budget": 2, "delay": .02, "mode": "recover"},
    {"name": "exhaust_429_503", "rows": 3, "workers": 3, "budget": 2, "delay": .02, "mode": "exhaust"},
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_csv(raw, expected_ids):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    rows = list(reader)
    valid = (reader.fieldnames == ["id", "answer"]
             and [row.get("id") for row in rows] == expected_ids
             and all(set(row) == {"id", "answer"}
                     and isinstance(row["answer"], str)
                     and 0 < len(row["answer"].strip()) <= 10000 for row in rows))
    if not valid:
        raise ValueError("Invalid CSV checkpoint")
    return rows


def mock_server(case):
    state = {"calls": [], "problems": [], "attempts": Counter(), "active": 0, "peak_active": 0, "selector_calls": 0, "answer_calls": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            # Keep only synthetic row numbers and HTTP metadata, never prompts.
            row = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise ValueError()
                raw = self.rfile.read(length)
                payload = json.loads(raw)
                messages = payload.get("messages", [])
                context = json.loads(messages[1]["content"])
                stage = context.get("stage", "answer")
                if stage not in {"answer", "evidence_selection"}:
                    raise ValueError()
                markers = set(MARKER.findall(raw.decode("utf-8")))
                if len(markers) != 1:
                    raise ValueError()
                row = int(markers.pop())
                if (self.path != "/v1/chat/completions" or payload.get("model") != "budget-mock"
                        or self.headers.get("Authorization") != "Bearer budget-mock-key"
                        or not 0 <= row < case["rows"]):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                with lock:
                    state["problems"].append("invalid_mock_request")
                self.send_error(400)
                return
            with lock:
                state["selector_calls" if stage == "evidence_selection" else "answer_calls"] += 1
                if stage == "evidence_selection":
                    state["problems"].append("selector_not_skipped_under_low_budget")
                state["attempts"][row] += 1
                attempt = state["attempts"][row]
                code = 200
                if case["mode"] in {"recover", "exhaust"} and row in (0, 1):
                    if attempt == 1 or case["mode"] == "exhaust":
                        code = 429 if row == 0 else 503
                state["calls"].append({"row": row, "attempt": attempt, "status": code})
                state["active"] += 1
                state["peak_active"] = max(state["peak_active"], state["active"])
            try:
                time.sleep(case["delay"])
                content = f"[MOCK] BUDGET_ROW_{row:04d}"
                body = json.dumps({"choices": [{"message": {"content": content},
                                                "finish_reason": "stop"}]}).encode()
                if code != 200:
                    body = b'{}'
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Retry-After", "0")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when the runtime's remaining deadline expires.
            finally:
                with lock:
                    state["active"] -= 1

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    return server, thread, state


def run_case(archive, members, case):
    expected_ids = [f"budget-{i:04d}" for i in range(case["rows"])]
    server, server_thread, state = mock_server(case)
    result = {"scenario": dict(case), "quality_verified": False}
    try:
        with tempfile.TemporaryDirectory(prefix="energytool-budget-") as folder:
            runtime = Path(folder)
            with ZipFile(archive) as bundle:
                bundle.extractall(runtime)
            data = runtime / "data"
            data.mkdir()
            with (data / "questions.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["id", "question"])
                writer.writerows((qid, f"Почему этот тестовый стенд подходит для проверки наших показаний BUDGET_ROW_{i:04d}?")
                                 for i, qid in enumerate(expected_ids))
            with ZipFile(data / "knowledge-base.zip", "w") as bundle:
                bundle.writestr("synthetic.md", "# Тестовый стенд\nСтенд хранит тестовые показания.\n")
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8",
                   "PYTHONDONTWRITEBYTECODE": "1", "DATA_DIR": "data",
                   "LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                   "LLM_API_KEY": "budget-mock-key", "LLM_MODEL": "budget-mock",
                   "MAX_WORKERS": str(case["workers"]), "LLM_ATTEMPTS": "2",
                   "LLM_TIMEOUT": "15", "RUN_BUDGET_SECONDS": str(case["budget"])}
            snapshots, invalid, initial_placeholders, timed_out = set(), [], False, False
            started = time.monotonic()
            with (runtime / "stdout.log").open("w+") as out, (runtime / "stderr.log").open("w+") as err:
                process = subprocess.Popen([sys.executable, "solution.py"], cwd=runtime,
                                           env=env, stdout=out, stderr=err)
                while process.poll() is None:
                    output = runtime / "submission.csv"
                    if output.exists():
                        try:
                            raw = output.read_bytes()
                            key = digest(raw)
                            if key not in snapshots:
                                records = inspect_csv(raw, expected_ids)
                                snapshots.add(key)
                                if not any(row["answer"].startswith("[MOCK]") for row in records):
                                    initial_placeholders = True
                        except (OSError, ValueError, UnicodeError, csv.Error) as exc:
                            if len(invalid) < 5:
                                invalid.append(type(exc).__name__)
                    if time.monotonic() - started > case["budget"] + 5:
                        process.kill()
                        timed_out = True
                        break
                    time.sleep(.005)
                process.wait(timeout=3)
                elapsed = time.monotonic() - started
                out.seek(0)
                events = []
                for line in out:
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict) and isinstance(event.get("statuses"), dict):
                            events.append(event)
                    except ValueError:
                        pass
                # Raw stdout/stderr stay in the temporary directory and are removed.
            stats = events[-1] if events else {}
            statuses = stats.get("statuses", {})
            final_raw = (runtime / "submission.csv").read_bytes()
            records = inspect_csv(final_raw, expected_ids)
            snapshots.add(digest(final_raw))
            mocked = sum(row["answer"] == f"[MOCK] BUDGET_ROW_{i:04d}"
                         for i, row in enumerate(records))
            misplaced = sum(row["answer"].startswith("[MOCK]")
                            and row["answer"] != f"[MOCK] BUDGET_ROW_{i:04d}"
                            for i, row in enumerate(records))
            failures = len(records) - mocked
            good_counts = (all(isinstance(v, int) and v >= 0 for v in statuses.values())
                           and sum(statuses.values()) == case["rows"]
                           and statuses.get("answered", 0) == mocked)
            expected = False
            if case["mode"] in {"healthy", "recover"}:
                expected = statuses == {"answered": case["rows"]} and failures == 0
            elif case["mode"] == "deadline":
                expected = (0 < mocked < case["rows"] and statuses.get("deadline_exceeded", 0) > 0
                            and set(statuses) <= {"answered", "deadline_exceeded"})
            elif case["mode"] == "exhaust":
                expected = statuses == {"answered": 1, "api_error": 2} and failures == 2
            attempts = dict(state["attempts"])
            retries_ok = all(value <= 2 for value in attempts.values())
            if case["mode"] in {"recover", "exhaust"}:
                retries_ok = retries_ok and attempts == {0: 2, 1: 2, 2: 1}
            else:
                retries_ok = retries_ok and all(value == 1 for value in attempts.values())
            unchanged = all(digest((runtime / name).read_bytes()) == sha for name, sha in members.items())
            passed = (process.returncode == 0 and not timed_out and elapsed <= case["budget"] + 3
                      and good_counts and expected and retries_ok and unchanged and not misplaced
                      and not invalid and len(snapshots) >= 2 and initial_placeholders
                      and not state["problems"] and state["peak_active"] <= case["workers"])
            result.update(passed=passed, exit_code=process.returncode, timeout=timed_out,
                          elapsed_seconds=round(elapsed, 3), runtime_statuses=statuses,
                          rows=len(records), mock_answers=mocked, technical_answers=failures,
                          expected_technical_failures=case["mode"] in {"deadline", "exhaust"},
                          no_false_answered_status=good_counts, csv_valid=True,
                          checkpoint_observation={"distinct_snapshots": len(snapshots),
                              "initial_full_placeholder_snapshot_seen": initial_placeholders,
                              "invalid_snapshot_errors": invalid,
                              "note": "Every observed snapshot contained all IDs; polling is not a proof of every possible filesystem race."},
                          api_calls=len(state["calls"]), selector_calls=state["selector_calls"],
                          answer_calls=state["answer_calls"], selector_skipped_under_low_budget=state["selector_calls"] == 0,
                          http_status_counts=dict(Counter(c["status"] for c in state["calls"])),
                          max_attempts_per_row=max(attempts.values(), default=0),
                          retry_bound_verified=retries_ok, peak_concurrent_requests=state["peak_active"],
                          request_problems=state["problems"], extracted_runtime_unchanged=unchanged)
    except (OSError, ValueError, csv.Error, subprocess.SubprocessError) as exc:
        result.update(passed=False, error_type=type(exc).__name__)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive, output = args.zip.resolve(), args.output.resolve()
    if output.exists():
        parser.error("Use a new output path to preserve previous evidence")
    before = digest(archive.read_bytes())
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        if (len(names) != len(set(names)) or not {"solution.py", "requirements.txt"} <= set(names)
                or any("/" in name or "\\" in name or name.startswith(".")
                       or not (name.endswith(".py") or name == "requirements.txt") for name in names)):
            parser.error("Expected root-only Python submission ZIP")
        members = {name: digest(bundle.read(name)) for name in names}
    results = []
    for case in CASES:
        result = run_case(archive, members, case)
        results.append(result)
        print(json.dumps({"scenario": case["name"], "passed": result["passed"]}), flush=True)
    after = digest(archive.read_bytes())
    report = {"mode": "mock_http_immutable_zip_budget", "zip_sha256": before,
              "zip_sha256_after": after, "zip_unchanged": before == after,
              "quality_verified": False, "external_model_calls": 0,
              "source_data": "synthetic only", "scenarios": results,
              "passed": before == after and all(result["passed"] for result in results)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "zip_sha256": before, "scenarios": len(results)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
