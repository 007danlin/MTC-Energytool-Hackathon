"""Platform entry point: DATA_DIR/{questions.csv,knowledge-base.zip} -> submission.csv."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import os
import platform
from pathlib import Path
import sys
import tempfile
import time

from consultant import TECHNICAL_ANSWER
from stable_consultant import StableConsultant as Consultant
from contracts import ConsultationRequest
from dialogue import parse_question
from llm_client import LLMClient
from retrieval import LexicalRetriever
from settings import ConfigurationError, Settings, env_first


def diagnostic(event, **fields):
    """Only explicitly selected metadata; never raw exceptions, URLs or answers."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), file=sys.stderr, flush=True)


def find_inputs(data_dir):
    """Keep input files paired; support the same legacy filenames as the sample."""
    directory = Path(data_dir)
    roots = [directory]
    if not directory.is_absolute():
        roots.append(Path(__file__).resolve().parent / directory)
    roots.append(Path.cwd())
    for root in dict.fromkeys(roots):
        questions = next((root / name for name in ("questions.csv", "train.csv") if (root / name).is_file()), None)
        knowledge = next((root / name for name in ("knowledge-base.zip", "knowledge_base.zip", "kb.zip") if (root / name).is_file()), None)
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


def run(rows, consultant, settings, output_path="submission.csv", *, deadline=None):
    deadline = deadline or time.monotonic() + settings.runtime_seconds
    answers = [TECHNICAL_ANSWER] * len(rows)
    statuses = []

    def work(index, question):
        if time.monotonic() >= deadline:
            return index, TECHNICAL_ANSWER, "deadline_exceeded"
        try:
            # Every CSV row has its own request; no shared lead or conversation state.
            request = ConsultationRequest(f"csv-{index}", parse_question(question))
            result = consultant.respond(request, deadline=deadline, answer_only=True)
            if result.status == "technical_error":
                diagnostic("case_error", row_number=index + 1,
                           error_code=result.debug.get("error_code"),
                           http_status=result.debug.get("http_status"))
            return index, result.answer, result.debug.get("error_code") or result.status
        except Exception as exc:
            # Do not log raw exception messages containing text, secrets or model payloads.
            diagnostic("case_error", row_number=index + 1, error_type=type(exc).__name__)
            return index, TECHNICAL_ANSWER, "case_error"

    # Create a complete, valid checkpoint before the first network call.
    # Technical placeholders are never reported as successful model answers.
    write_submission(output_path, rows, answers)
    with ThreadPoolExecutor(max_workers=settings.workers) as pool:
        futures = [pool.submit(work, i, question) for i, (_, question) in enumerate(rows)]
        for completed, future in enumerate(as_completed(futures), 1):
            index, answer, status = future.result()
            answers[index] = answer
            statuses.append(status)
            # Atomic checkpoints ensure every ID is present even during a partial run.
            if completed % 10 == 0 or completed == len(rows):
                write_submission(output_path, rows, answers)
                diagnostic("checkpoint", completed=completed, total=len(rows))
    return statuses


def main():
    started = time.monotonic()
    stage = "configuration"
    diagnostic("startup", python=platform.python_version())
    try:
        settings = Settings.from_env()
        diagnostic("configuration_ready", workers=settings.workers, max_tokens=settings.max_tokens,
                   timeout_seconds=settings.timeout, mode="answer_only")
        stage = "input"
        questions_path, knowledge_path = find_inputs(env_first("DATA_DIR", default="data"))
        rows = read_questions(questions_path)
        stage = "knowledge_base"
        retriever = LexicalRetriever.from_zip(knowledge_path)
        diagnostic("inputs_ready", rows=len(rows), fragments=len(retriever.fragments))
        service = Consultant(LLMClient(settings), retriever, settings)
        stage = "generation"
        statuses = run(rows, service, settings, deadline=started + settings.runtime_seconds)
        print(json.dumps({"rows": len(rows), "elapsed_seconds": round(time.monotonic() - started, 2),
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
