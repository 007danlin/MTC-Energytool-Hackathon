"""Platform entry point: DATA_DIR/{questions.csv,knowledge-base.zip} -> submission.csv."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import math
import os
import platform
from pathlib import Path
import sys
import tempfile
import threading
import time

from consultant import Consultant, LAST_RESORT, TECHNICAL_ANSWER
from llm_client import LLMClient
from settings import ConfigurationError, Settings, env_first


def diagnostic(event, **fields):
    """Only explicitly selected metadata; never raw exceptions, addresses, questions or answers."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), file=sys.stderr, flush=True)


def find_inputs(data_dir):
    """Keep the two input files paired; support the legacy names of the organizers' sample."""
    directory = Path(data_dir)
    roots = [directory]
    if not directory.is_absolute():
        roots.append(Path(__file__).resolve().parent / directory)
    roots.append(Path.cwd())
    for root in dict.fromkeys(roots):
        questions = next((root / name for name in ("questions.csv", "train.csv") if (root / name).is_file()), None)
        knowledge = next((root / name for name in ("knowledge-base.zip", "knowledge_base.zip", "kb.zip")
                          if (root / name).is_file()), None)
        if questions and knowledge:
            return questions, knowledge
    raise FileNotFoundError("Input pair not found")


def read_questions(path):
    csv.field_size_limit(2_000_000)
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if (not {"id", "question"}.issubset(headers) or len(set(headers)) != len(headers)
                or any(not name for name in headers)):
            raise ValueError("questions.csv must contain unique id and question columns")
        rows, ids = [], set()
        for row in reader:
            qid, question = row.get("id"), row.get("question")
            if (not qid or not qid.strip() or qid in ids or not question or not question.strip()
                    or None in row or len(question) > 100000):
                raise ValueError("Invalid, empty or duplicate input row")
            ids.add(qid)
            rows.append((qid, question))
        if not rows:
            raise ValueError("questions.csv is empty")
    return rows


def write_submission(path, rows, answers):
    if len(rows) != len(answers) or len({qid for qid, _ in rows}) != len(rows):
        raise ValueError("Output cardinality mismatch")
    if any(not isinstance(a, str) or not a.strip() or len(a) > 10000 for a in answers):
        raise ValueError("Every answer must contain 1..10000 characters")
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=".submission-", suffix=".csv", delete=False) as stream:
            temporary = stream.name
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["id", "answer"])
            writer.writerows((qid, answer) for (qid, _), answer in zip(rows, answers))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class Gate:
    """Adjustable number of rows processed at the same time."""
    def __init__(self, limit):
        self._changed = threading.Condition()
        self.limit, self._active = limit, 0

    def __enter__(self):
        with self._changed:
            while self._active >= self.limit:
                self._changed.wait()
            self._active += 1

    def __exit__(self, *exc):
        with self._changed:
            self._active -= 1
            self._changed.notify_all()

    def set(self, limit):
        with self._changed:
            self.limit = max(1, limit)
            self._changed.notify_all()


def run(rows, consultant, settings, output_path="submission.csv", *, deadline=None, client=None):
    started = time.monotonic()
    deadline = deadline or started + settings.runtime_seconds
    control = not settings.rescue
    placeholder = TECHNICAL_ANSWER if control else LAST_RESORT
    answers = [placeholder] * len(rows)
    statuses, modes, seconds = [], [], []
    gate = Gate(settings.workers)
    cap = settings.workers if control else max(settings.workers, settings.workers_cap)

    def work(index, question):
        with gate:
            begun = time.monotonic()
            if begun >= deadline:
                if control:
                    return index, TECHNICAL_ANSWER, {"status": "deadline_exceeded"}
                return index, consultant.extract(question), {"status": "deadline_fallback"}
            try:
                # Every CSV row is an independent request: no dialogue or lead state is shared.
                answer, info = consultant.answer(question, deadline=deadline)
                return index, answer, dict(info, seconds=time.monotonic() - begun)
            except Exception as exc:
                # Never log raw exception text: it may contain questions or model payloads.
                return index, placeholder, {"status": "case_error", "error": type(exc).__name__}

    # A complete, valid file exists before the first network call and after every tenth row.
    write_submission(output_path, rows, answers)
    review_at = max(6, 2 * settings.workers)   # rows to finish before the pace is judged
    limited_at_raise, may_raise = None, True
    with ThreadPoolExecutor(max_workers=cap) as pool:
        futures = [pool.submit(work, i, question) for i, (_, question) in enumerate(rows)]
        for completed, future in enumerate(as_completed(futures), 1):
            index, answer, info = future.result()
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 10000:
                answer, info = placeholder, dict(info, status="invalid_answer")
            answers[index] = answer
            statuses.append(info.get("status", "unknown"))
            modes.append(info.get("mode", "unknown"))
            if isinstance(info.get("seconds"), float):
                seconds.append(info["seconds"])
            if info.get("status") != "ok":
                diagnostic("case", row_number=index + 1, **{k: info.get(k) for k in (
                    "status", "error", "mode", "calls", "finish", "reasoning_chars", "completion_tokens")})
            # Time guard. The pace is judged on finished rows only (never on the first few). When the
            # remaining rows would not fit the budget, first more rows are processed in parallel; the
            # compact context without reasoning is the last measure, after parallelism is exhausted.
            remaining_rows = len(rows) - completed
            limited = client.rate_limited if client is not None else 0
            if limited_at_raise is not None and limited > limited_at_raise + 2:
                # The service answered the extra parallel rows with rate limits: back to the configured number.
                gate.set(settings.workers)
                limited_at_raise, may_raise = None, False
                diagnostic("pace", completed=completed, total=len(rows), workers=gate.limit)
            if not control and remaining_rows and completed >= review_at and seconds:
                now = time.monotonic()
                recent = seconds[-24:]
                per_row = sum(recent) / len(recent)
                left = deadline - now
                if remaining_rows * per_row / gate.limit > left * 0.85:
                    if gate.limit < cap and may_raise and not limited:
                        needed = math.ceil(remaining_rows * per_row / max(left * 0.7, 1.0))
                        gate.set(min(cap, max(gate.limit + 1, needed)))
                        limited_at_raise = limited
                        review_at = completed + max(4, gate.limit)   # judge the new pace on fresh rows
                        diagnostic("pace", completed=completed, total=len(rows), workers=gate.limit)
                    elif not consultant.state.fast:
                        consultant.state.hurry()
                        review_at = completed + max(4, gate.limit)
                        diagnostic("pace", completed=completed, total=len(rows), switched_to="fast")
            if completed % 10 == 0 or completed == len(rows):
                write_submission(output_path, rows, answers)
                diagnostic("checkpoint", completed=completed, total=len(rows))
    return statuses, modes, gate.limit


def main():
    started = time.monotonic()
    stage = "configuration"
    diagnostic("startup", python=platform.python_version(), build="n2")
    try:
        settings = Settings.from_env()
        diagnostic("configuration_ready", workers=settings.workers, max_tokens=settings.max_tokens,
                   main_max_tokens=settings.main_max_tokens, timeout_seconds=settings.timeout,
                   prompt=settings.prompt, context=settings.context, reasoning=settings.reasoning,
                   rescue=settings.rescue, fewshot=settings.fewshot, top_k=settings.top_k, control=settings.control,
                   retry_tokens=settings.retry_tokens, retry_reasoning=settings.retry_reasoning,
                   think_temperature=settings.think_temperature, style=settings.style, quick=settings.quick)
        stage = "input"
        questions_path, knowledge_path = find_inputs(env_first("DATA_DIR", default="data"))
        rows = read_questions(questions_path)
        stage = "knowledge_base"
        client = LLMClient(settings)
        service = Consultant(client, knowledge_path, settings)
        diagnostic("inputs_ready", rows=len(rows), fragments=len(service.fragments))
        stage = "generation"
        statuses, modes, workers = run(rows, service, settings, deadline=started + settings.runtime_seconds, client=client)
        print(json.dumps({"rows": len(rows), "elapsed_seconds": round(time.monotonic() - started, 2),
                          "api_calls": client.calls, "context_at_end": service.state.mode(), "workers_at_end": workers,
                          "fast_mode": service.state.fast, "window_chars": service.state.allowed_chars(),
                          "modes": {m: modes.count(m) for m in sorted(set(modes))},
                          "statuses": {s: statuses.count(s) for s in sorted(set(statuses))}}, ensure_ascii=False))
        return 0
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        diagnostic("setup_error", stage=stage, error_type=type(exc).__name__)
        print("Input/setup error: check DATA_DIR, CSV and knowledge-base.zip", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
