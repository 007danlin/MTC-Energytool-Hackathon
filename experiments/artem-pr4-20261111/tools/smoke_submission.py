"""Run the built ZIP in an isolated directory against a local mock HTTP API."""
import argparse
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from zipfile import ZipFile


def csv_request_problems(messages):
    """Validate the CSV API structure without prescribing prompt wording."""
    problems = []
    if (not isinstance(messages, list) or len(messages) != 2
            or not all(isinstance(message, dict) for message in messages)):
        return ["wrong message envelope"]
    if [message.get("role") for message in messages] != ["system", "user"]:
        problems.append("wrong message roles")
    if not isinstance(messages[0].get("content"), str) or not messages[0]["content"].strip():
        problems.append("missing system prompt")
    try:
        context = json.loads(messages[1].get("content", ""))
    except (TypeError, ValueError):
        return problems + ["invalid context JSON"]
    if not isinstance(context, dict):
        return problems + ["context must be an object"]
    if "lead_so_far" in context:
        problems.append("CSV must not request structured lead extraction")
    history = context.get("messages")
    if (not isinstance(history, list) or not history
            or not all(isinstance(message, dict)
                       and message.get("role") in {"user", "assistant"}
                       and isinstance(message.get("content"), str)
                       for message in history)
            or history[-1].get("role") != "user"):
        problems.append("invalid conversation history")
    sources = context.get("sources")
    if (not isinstance(sources, list)
            or not all(isinstance(source, dict)
                       and isinstance(source.get("source_id"), str)
                       and isinstance(source.get("text"), str) for source in sources)):
        problems.append("invalid source fragments")
    return problems


def request_identity(messages):
    context = json.loads(messages[1]["content"])
    stage = context.get("stage", "answer")
    key = hashlib.sha256(json.dumps(context["messages"], ensure_ascii=False,
                                   sort_keys=True).encode()).hexdigest()
    return context, stage, key


PLAN_PROBE = r"""
import hashlib,json,sys,time
from pathlib import Path
from consultant import Consultant
from contracts import ConsultationRequest
from dialogue import parse_question
from retrieval import LexicalRetriever,load_fragments
from settings import Settings
from solution import read_questions
plan={}
class ProbeClient:
    def record(self,messages,stage):
        context=json.loads(messages[1]['content'])
        key=hashlib.sha256(json.dumps(context['messages'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        item=plan.setdefault(key,{'selector':0,'answer':0})
        item[stage]+=1
        return context
    def complete_once(self,messages,**kwargs):
        context=self.record(messages,'selector')
        source=next(s for s in context['sources'] if len(s['text'].strip())>=12)
        return json.dumps({'evidence':[{'source_id':source['source_id'],'quote':source['text'][:256]}]},ensure_ascii=False)
    def complete(self,messages,**kwargs):
        self.record(messages,'answer')
        return '[MOCK] План вызовов без HTTP.'
data=Path(sys.argv[1])
settings=Settings('http://localhost/v1','local-mock-key','local-mock-model',timeout=15,attempts=2)
service=Consultant(ProbeClient(),LexicalRetriever(load_fragments(data/'knowledge-base.zip')),settings)
for qid,question in read_questions(data/'questions.csv'):
    service.respond(ConsultationRequest(qid,parse_question(question)),answer_only=True,deadline=time.monotonic()+1000)
print(json.dumps(plan))
"""


def expected_stage_counts(runtime, data):
    """Probe immutable runtime routing with a scripted client; never perform HTTP."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-c", PLAN_PROBE, str(data)], cwd=runtime,
                            env=env, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Cannot establish stage expectations: " + result.stderr[-2000:])
    return json.loads(result.stdout)


def archive_stage_counts(archive, data):
    with tempfile.TemporaryDirectory(prefix="energytool-stage-plan-") as folder:
        with ZipFile(archive) as bundle:
            bundle.extractall(folder)
        return expected_stage_counts(Path(folder), data)


def assert_metrics(metrics, plan, *, selector_failures=0, answer_rate_limits=0):
    expected_selectors = sum(item["selector"] for item in plan.values())
    expected_answers = sum(item["answer"] for item in plan.values())
    assert not metrics["problems"], metrics["problems"]
    assert metrics["selector_calls"] == expected_selectors, metrics
    assert metrics["answer_calls"] == expected_answers + answer_rate_limits, metrics
    assert metrics["calls"] == expected_selectors + expected_answers + answer_rate_limits, metrics
    assert metrics["selector_failures"] == selector_failures, metrics
    assert metrics["rate_limited"] == answer_rate_limits, metrics
    assert set(metrics["by_history"]) == set(plan), metrics
    for key, expected in plan.items():
        actual = metrics["by_history"][key]
        assert actual["selector"] == expected["selector"], (key, actual, expected)
        assert actual["answer"] - actual["answer_rate_limited"] == expected["answer"], (key, actual, expected)
        assert actual["selector_failed"] <= actual["selector"], (key, actual)
    return True


class Handler(BaseHTTPRequestHandler):
    calls = 0
    selector_calls = 0
    answer_calls = 0
    problems = []
    by_history = {}
    rate_limits_remaining = 0
    rate_limited = 0
    selector_failures_remaining = 0
    selector_failures = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls, *, rate_limits=0, selector_errors=0):
        cls.calls = cls.selector_calls = cls.answer_calls = 0
        cls.problems, cls.by_history = [], {}
        cls.rate_limits_remaining, cls.rate_limited = rate_limits, 0
        cls.selector_failures_remaining, cls.selector_failures = selector_errors, 0

    @classmethod
    def metrics(cls):
        with cls.lock:
            return {"calls": cls.calls, "selector_calls": cls.selector_calls,
                    "answer_calls": cls.answer_calls, "problems": list(cls.problems),
                    "rate_limited": cls.rate_limited, "selector_failures": cls.selector_failures,
                    "by_history": {key: dict(value) for key, value in cls.by_history.items()}}

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path not in ("/health", "/metrics"):
            self.send_error(404)
            return
        body = json.dumps(Handler.metrics()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        problems = []
        if self.path != "/v1/chat/completions":
            problems.append("wrong endpoint")
        if request.get("model") != "local-mock-model":
            problems.append("wrong model")
        if self.headers.get("Authorization") != "Bearer local-mock-key":
            problems.append("wrong auth")
        problems.extend(csv_request_problems(request.get("messages")))
        if problems:
            with self.lock:
                Handler.problems.extend(problems)
            self.send_error(400)
            return
        context, stage, key = request_identity(request["messages"])
        if stage not in ("answer", "evidence_selection"):
            problems.append("unknown request stage")
        is_selector = stage == "evidence_selection"
        if is_selector:
            if context.get("current_question") != context["messages"][-1]["content"]:
                problems.append("selector current question differs from last user message")
            if not context["sources"]:
                problems.append("selector needs original sources")
            if not isinstance(request.get("max_tokens"), int) or not 1 <= request["max_tokens"] <= 512:
                problems.append("selector token budget outside contract")
        with self.lock:
            Handler.calls += 1
            Handler.problems.extend(problems)
            record = Handler.by_history.setdefault(key, {"selector": 0, "answer": 0,
                                                        "selector_failed": 0, "answer_rate_limited": 0})
            code = 200
            if is_selector:
                Handler.selector_calls += 1
                record["selector"] += 1
                if Handler.selector_failures_remaining:
                    Handler.selector_failures_remaining -= 1
                    Handler.selector_failures += 1
                    record["selector_failed"] += 1
                    code = 503
            else:
                Handler.answer_calls += 1
                record["answer"] += 1
                if Handler.rate_limits_remaining:
                    Handler.rate_limits_remaining -= 1
                    Handler.rate_limited += 1
                    record["answer_rate_limited"] += 1
                    code = 429
        if code != 200:
            self.send_response(code)
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if is_selector:
            source = next((s for s in context["sources"] if len(s["text"].strip()) >= 12), None)
            if source is None:
                with self.lock:
                    Handler.problems.append("selector has no quotable original source")
                result = '{"evidence":[]}'
            else:
                quote = source["text"][:256]
                assert quote in source["text"] and len(quote.strip()) >= 12
                result = json.dumps({"evidence": [{"source_id": source["source_id"], "quote": quote}]}, ensure_ascii=False)
        else:
            result = "[MOCK] Протокол работает. Качество генерации не проверено."
        response = json.dumps({"choices": [{"message": {"content": result},
                                            "finish_reason": "stop"}]}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def smoke_once(archive, data, *, inject_errors=False):
    plan = archive_stage_counts(archive, data)
    selector_errors = int(inject_errors and any(item["selector"] for item in plan.values()))
    Handler.reset(rate_limits=int(inject_errors), selector_errors=selector_errors)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="energytool-submission-") as folder:
            directory = Path(folder)
            with ZipFile(archive) as bundle:
                if any("/" in n or "\\" in n or n.startswith(".") for n in bundle.namelist()):
                    raise ValueError("ZIP must contain root files only")
                bundle.extractall(directory)
            (directory / "data").mkdir()
            for name in ("questions.csv", "knowledge-base.zip"):
                shutil.copyfile(data / name, directory / "data" / name)
            # Do not inherit any live model credentials or PYTHONPATH.
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8",
                   "LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1", "LLM_API_KEY": "local-mock-key",
                   "LLM_MODEL": "local-mock-model", "MAX_WORKERS": "3",
                   "RETRIEVAL_MODE": "a2",  # Chat-only mock; hybrid has its own integration suite.
                   "LLM_TIMEOUT": "15", "LLM_ATTEMPTS": "2"}
            process = subprocess.run([sys.executable, "solution.py"], cwd=directory, env=env,
                                     capture_output=True, text=True, timeout=60)
            if process.returncode:
                raise RuntimeError("Extracted solution failed: " + process.stderr)
            with (directory / "submission.csv").open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                assert reader.fieldnames == ["id", "answer"]
                records = list(reader)
            with (data / "questions.csv").open(encoding="utf-8-sig", newline="") as stream:
                ids = [r["id"] for r in csv.DictReader(stream)]
            assert [r["id"] for r in records] == ids
            assert len(set(ids)) == len(ids)
            assert all(0 < len(r["answer"]) <= 10000 for r in records)
            assert all(r["answer"].startswith("[MOCK]") for r in records)
            metrics = Handler.metrics()
            assert sum(item["answer"] for item in plan.values()) == len(ids)
            assert_metrics(metrics, plan, selector_failures=selector_errors,
                           answer_rate_limits=int(inject_errors))
            return {"mode": "mock_http_isolated_zip", "rows": len(records), "api_calls": metrics["calls"],
                    "selector_calls": metrics["selector_calls"], "answer_calls": metrics["answer_calls"],
                    "selector_failures": metrics["selector_failures"], "answer_rate_limits": metrics["rate_limited"],
                    "stage_counts_exact": True, "csv_valid": True,
                    "exit_code": process.returncode, "quality_verified": False}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def smoke(archive, data):
    healthy = smoke_once(archive, data)
    healthy["fault_injection"] = smoke_once(archive, data, inject_errors=True)
    return healthy


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=Path("artifacts/daniel-submission.zip"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--serve", action="store_true", help="Serve fixture inside an isolated Docker network")
    parser.add_argument("--rate-limit-once", action="store_true")
    parser.add_argument("--selector-error-once", action="store_true")
    args = parser.parse_args()
    if args.serve:
        Handler.reset(rate_limits=int(args.rate_limit_once), selector_errors=int(args.selector_error_once))
        ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
    else:
        print(json.dumps(smoke(args.zip.resolve(), args.data_dir.resolve()), ensure_ascii=False, indent=2))
