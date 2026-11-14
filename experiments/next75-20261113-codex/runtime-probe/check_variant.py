"""Use real localhost HTTP exchanges, without invoking any language model."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

parser = argparse.ArgumentParser()
parser.add_argument("variant", choices=("exact", "patched", "local"))
parser.add_argument("--source", type=Path)
parser.add_argument("--out", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent
bundle = root.parent / "handoff"
sys.path.insert(0, str(args.source or (bundle / "winner/source" if args.variant == "exact" else root / ("candidate-local" if args.variant == "local" else "candidate"))))
from llm_client import LLMClient, ModelError
from settings import Settings
from consultant import Consultant

traces = []
scenario = ""
counts = {}
window = None
GOOD = {"choices": [{"message": {"content": "Это проверочный ответ имитатора, а не оценка качества."}, "finish_reason": "stop"}], "usage": {"completion_tokens": 10}}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        global window
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        payload = json.loads(raw)
        counts[scenario] = counts.get(scenario, 0) + 1
        row_one = payload["messages"][-1]["content"] == "row-one"
        status, body = 200, GOOD
        if row_one:
            if scenario in ("mixed", "mixed-low", "mixed-retry") and payload["max_tokens"] > 2048:
                status, body = 400, {"error": {"message": "max_tokens is too large: maximum context length is 32768 tokens and your request has 30000 input tokens"}}
            elif scenario == "output-cap" and payload["max_tokens"] > 2048:
                status, body = 400, {"error": {"message": "max_tokens must be at most 2048"}}
            elif scenario == "cap-with-window-fitting" and payload["max_tokens"] > 2048:
                status, body = 400, {"error": {"message": "max_tokens must be at most 2048; maximum context length is 32768 tokens; request has 1000 input tokens"}}
            elif scenario == "ambiguous" and payload["max_tokens"] > 2048:
                status, body = 400, {"error": {"message": "max_tokens too large for context"}}
            elif scenario == "ambiguous-numbers" and payload["max_tokens"] > 2048:
                status, body = 400, {"error": {"message": "max_tokens must be at most 2048; maximum context length is 32768 tokens; model output identifier 131072"}}
            elif scenario == "context-only":
                status, body = 400, {"error": {"message": "maximum context length is 32768 tokens; your request has 33000 input tokens"}}
            elif scenario in ("context-only-below-window", "context-only-below-window-low"):
                status, body = 400, {"error": {"message": "maximum context length is 32768 tokens; your request has 30000 input tokens"}}
            elif scenario == "mixed-413":
                status, body = 413, {"error": {"message": "max_tokens is too large: maximum context length is 32768 tokens and your request has 30000 input tokens"}}
            elif scenario in ("generic-400", "generic-404", "generic-422"):
                status, body = int(scenario[-3:]), {"error": {"message": "Invalid request shape"}}
            elif scenario == "http-413":
                status, body = 413, {"error": {"message": "Request entity too large"}}
        if scenario == "consultant" and "Мощность объекта 500 кВт." in payload["messages"][-1]["content"]:
            tokens = sum(len(m["content"]) for m in payload["messages"]) // 2
            if window is None:
                window = tokens + 2048
            if tokens + payload["max_tokens"] > window:
                status, body = 400, {"error": {"message": f"max_tokens is too large: maximum context length is {window} tokens and your request has {tokens} input tokens"}}
        response = json.dumps(body, ensure_ascii=False).encode()
        traces.append({"scenario": scenario, "request_number": counts[scenario], "raw_payload_utf8": raw.decode(), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "response_status": status, "response_body": body})
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
cfg = Settings(f"http://127.0.0.1:{server.server_address[1]}/v1", "test", "test")
results = {}
try:
    for scenario in ("healthy", "mixed", "mixed-low", "mixed-retry", "output-cap", "cap-with-window-fitting", "ambiguous", "ambiguous-numbers", "context-only", "context-only-below-window", "context-only-below-window-low", "mixed-413", "generic-400", "generic-404", "generic-422", "http-413"):
        client = LLMClient(cfg)
        rows = []
        for content in ("row-one", "row-two"):
            try:
                done = client.chat([{"role": "user", "content": content}], max_tokens=8192 if scenario == "mixed-retry" else 4096, reasoning="low" if scenario in ("mixed-low", "context-only-below-window-low") else "default")
                rows.append({"finished": True, "finish_reason": done.finish_reason, "content": done.content})
            except ModelError as exc:
                rows.append({"finished": False, "code": exc.code, "context_overflow": exc.context_overflow, "window": exc.window, "refused_limit": exc.limit})
        requests = [t for t in traces if t["scenario"] == scenario]
        results[scenario] = {"rows": rows, "limits": [json.loads(t["raw_payload_utf8"])["max_tokens"] for t in requests], "calls": client.calls, "remembered_cap": client._max_tokens_cap}
    scenario = "consultant"
    client = LLMClient(cfg)
    knowledge = bundle / "sources/organizers/drive-download-20261109T164943Z-1-001/knowledge-base.zip"
    service = Consultant(client, knowledge, cfg)
    answers = []
    for question in ("Мощность объекта 500 кВт. Подходит ли оптовый рынок?", "Можно ли подключить АСКУЭ в СНТ?"):
        answer, info = service.answer(question)
        answers.append({"answer": answer, "info": info})
    requests = [t for t in traces if t["scenario"] == scenario]
    results[scenario] = {"answers": answers, "limits": [json.loads(t["raw_payload_utf8"])["max_tokens"] for t in requests], "prompt_chars": [sum(len(m["content"]) for m in json.loads(t["raw_payload_utf8"])["messages"]) for t in requests], "calls": client.calls, "remembered_cap": client._max_tokens_cap, "allowed_chars": service.state.allowed_chars(), "mode": service.state.mode()}
finally:
    server.shutdown()
    server.server_close()

output = args.out or root
output.mkdir(parents=True, exist_ok=True)
(output / f"{args.variant}-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
(output / f"{args.variant}-http.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in traces))
print(json.dumps({k: {x: v[x] for x in ("limits", "calls", "remembered_cap")} for k, v in results.items()}, ensure_ascii=False, indent=2))
