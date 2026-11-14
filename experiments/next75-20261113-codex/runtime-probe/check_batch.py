"""209-row HTTP protocol experiment with one shared runtime deadline; no model."""
import sys
sys.dont_write_bytecode = True
import argparse
from collections import Counter
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

p = argparse.ArgumentParser()
p.add_argument("variant", choices=("exact", "local"))
p.add_argument("scenario", choices=("healthy", "mixed-repeated", "mixed-repeated-delayed"))
args = p.parse_args()
root = Path(__file__).resolve().parent
out = root / "batch209" / f"{args.variant}-{args.scenario}"
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root.parent / "n2-test-reference/tools"))
from paths import all_questions, KB
sys.path.insert(0, str(root.parent / "handoff/winner/source" if args.variant == "exact" else root / "candidate-local"))
from consultant import Consultant
from llm_client import LLMClient, HTTPTransport
from settings import Settings
from solution import read_questions, run

payload_file = (out / "http.jsonl").open("w", encoding="utf-8")
lock = threading.Lock()
local = threading.local()
traces = []

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        payload = json.loads(raw)
        if args.scenario.startswith("mixed-repeated") and payload["max_tokens"] > 2048:
            status = 400
            body = {"error": {"message": "max_tokens is too large: maximum context length is 32768 tokens and your request has 30000 input tokens"}}
        else:
            status = 200
            body = {"choices": [{"message": {"content": "Проверочный ответ имитатора. Он не оценивает фактическое качество консультации."}, "finish_reason": "stop"}], "usage": {"completion_tokens": 16}}
        if args.scenario == "mixed-repeated-delayed":
            time.sleep(0.15)
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

class CaptureTransport(HTTPTransport):
    def post(self, url, headers, payload, timeout):
        started = time.monotonic()
        status, response_headers, raw = super().post(url, headers, payload, timeout)
        data = json.loads(payload)
        event = {"question_sha256": local.question_hash, "payload_sha256": hashlib.sha256(payload).hexdigest(), "payload_bytes": len(payload), "raw_payload_utf8": payload.decode(), "effective_model": data["model"], "effective_max_tokens": data["max_tokens"], "status": status, "elapsed": time.monotonic() - started, "response": json.loads(raw)}
        with lock:
            payload_file.write(json.dumps(event, ensure_ascii=False) + "\n")
            payload_file.flush()
            traces.append({k:v for k,v in event.items() if k not in ("raw_payload_utf8", "response")})
        return status, response_headers, raw

class CaptureConsultant(Consultant):
    def answer(self, question, **kwargs):
        local.question_hash = hashlib.sha256(question.encode()).hexdigest()
        return super().answer(question, **kwargs)

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
cfg = Settings(f"http://127.0.0.1:{server.server_address[1]}/v1", "test", "test", runtime_seconds=12.0 if args.scenario == "mixed-repeated-delayed" else 1120.0)
rows = read_questions(all_questions(out / "questions.csv"))
assert len(rows) == 209
started = time.monotonic()
client = LLMClient(cfg, transport=CaptureTransport())
service = CaptureConsultant(client, KB, cfg)
try:
    statuses, modes, workers = run(rows, service, cfg, str(out / "submission.csv"), deadline=started + cfg.runtime_seconds, client=client)
    elapsed = time.monotonic() - started
finally:
    payload_file.close()
    server.shutdown()
    server.server_close()
with (out / "submission.csv").open(encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    submitted = list(reader)
assert fields == ["id", "answer"]
assert [r["id"] for r in submitted] == [r[0] for r in rows]
assert all(r["answer"].strip() for r in submitted)
summary = {"variant": args.variant, "scenario": args.scenario, "rows": len(rows), "shared_runtime_budget_seconds": cfg.runtime_seconds, "elapsed_seconds": elapsed, "http_attempts": client.calls, "http_refusals": sum(t["status"] != 200 for t in traces), "limits": dict(Counter(t["effective_max_tokens"] for t in traces)), "statuses": dict(Counter(statuses)), "modes": dict(Counter(modes)), "workers_end": workers, "fast_end": service.state.fast, "allowed_chars": service.state.allowed_chars(), "learned_output_cap": client._max_tokens_cap, "all_ids_valid": True, "model_generated": False, "limitation": "Immediate mock responses, artificial token counters; does not validate real model quality or 20-minute provider latency."}
if args.scenario == "mixed-repeated-delayed":
    summary["response_delay_seconds"] = 0.15
    summary["limitation"] = "Mock responses with 150ms delay per HTTP, artificial token counters; does not validate real model quality or 20-minute provider latency."
(out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
(out / "payload-hashes.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
