"""Run the built ZIP against a local mock proxy and check hybrid retrieval failure modes.

No real platform calls. Chat answers are stubs: this checks integration, budget and
fallbacks, not answer quality. Questions: eval/cases_v3.json (passed as input data,
never packed into the ZIP).

  python tools/hybrid_integration_check.py                 # fast fake embeddings, all scenarios
  .venv/Scripts/python tools/hybrid_integration_check.py --real-embeddings --scenarios ok
"""
import argparse
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_submission import build  # noqa: E402

STATE = {"mode": "ok", "emb_calls": 0, "chat_calls": 0, "rerank_calls": 0, "model": None,
         "lock": threading.Lock()}


def fake_vector(text, dim=1024):
    v = [0.0] * dim
    for word in text.lower().split():
        h = int(hashlib.md5(word.encode("utf8")).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        mode = STATE["mode"]
        if self.path.endswith("/embeddings"):
            with STATE["lock"]:
                STATE["emb_calls"] += 1
                calls = STATE["emb_calls"]
            texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
            startup = len(texts) > 2  # start-up batches carry 16 fragments
            if mode == "emb_500" or (mode == "query_500" and not startup):
                return self._send(500, {"error": "unavailable"})
            if mode == "query_hang" and not startup:
                time.sleep(12)
            if mode == "dim_mismatch" and calls == 2:
                return self._send(200, {"data": [{"index": i, "embedding": [0.1] * 7} for i in range(len(texts))]})
            if STATE["model"] is not None:
                vecs = STATE["model"].encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
            else:
                vecs = [fake_vector(t) for t in texts]
            return self._send(200, {"data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]})
        if self.path.endswith("/rerank"):
            with STATE["lock"]:
                STATE["rerank_calls"] += 1
            n = min(body.get("top_n", len(body["documents"])), len(body["documents"]))
            return self._send(200, {"results": [{"index": i, "relevance_score": 1.0 - i / 100} for i in range(n)]})
        if self.path.endswith("/chat/completions"):
            with STATE["lock"]:
                STATE["chat_calls"] += 1
            return self._send(200, {"choices": [{"message": {"content": "Тестовый ответ."}, "finish_reason": "stop"}]})
        self._send(404, {})


def run_case(workdir, port, extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "OPENAI_", "EMB", "RERANK"))}
    env.update(LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="test-key", LLM_MODEL="test-model",
               EMB_MODEL="baai/bge-m3", DATA_DIR=str(workdir / "data"), MAX_WORKERS="3", PYTHONIOENCODING="utf-8")
    env.update(extra_env)
    started = time.time()
    proc = subprocess.run([sys.executable, "solution.py"], cwd=workdir / "app", env=env,
                          capture_output=True, text=True, encoding="utf8", timeout=1200)
    elapsed = time.time() - started
    if not (workdir / "app" / "submission.csv").exists():
        raise RuntimeError(f"no submission.csv, exit={proc.returncode}: {proc.stderr[-800:]}")
    summary = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    with open(workdir / "app" / "submission.csv", encoding="utf8", newline="") as f:
        rows = list(csv.DictReader(f))
    events = [json.loads(l) for l in proc.stderr.splitlines() if l.startswith("{")]
    ready = next((e for e in events if e.get("event") == "inputs_ready"), {})
    return {"exit": proc.returncode, "elapsed_s": round(elapsed, 1), "rows": len(rows),
            "empty": sum(not r["answer"].strip() for r in rows), "ids": [r["id"] for r in rows],
            "startup_mode": ready.get("retrieval"), "startup_error": ready.get("retrieval_startup_error"),
            "final_retrieval": summary.get("retrieval"), "statuses": summary.get("statuses")}


EXPECT = {
    "ok": lambda r: r["startup_mode"] == "hybrid" and r["final_retrieval"]["fallback_searches"] == 0,
    "emb_500": lambda r: r["startup_mode"] == "lexical_fallback",
    "dim_mismatch": lambda r: r["startup_mode"] == "lexical_fallback",
    "query_500": lambda r: r["startup_mode"] == "hybrid" and r["final_retrieval"]["breaker_open"],
    "query_hang": lambda r: r["final_retrieval"]["breaker_open"] and r["elapsed_s"] < 120,
    "forced_a2": lambda r: r["startup_mode"] == "a2_forced",
    "rerank": lambda r: r["startup_mode"] == "hybrid" and STATE["rerank_calls"] > 0,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenarios", default=",".join(EXPECT))
    p.add_argument("--real-embeddings", action="store_true")
    p.add_argument("--output", default=str(ROOT / "reports/private/hybrid-integration.json"))
    args = p.parse_args()
    if args.real_embeddings:
        from sentence_transformers import SentenceTransformer
        STATE["model"] = SentenceTransformer("BAAI/bge-m3", device="cpu")

    cases = json.loads((ROOT / "eval/cases_v3.json").read_text(encoding="utf8"))["cases"]
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        manifest = build(tmp / "candidate.zip")
        (tmp / "app").mkdir()
        with ZipFile(tmp / "candidate.zip") as z:
            z.extractall(tmp / "app")
            packed = z.namelist()
        assert not any(n.endswith((".json", ".csv", ".zip")) or "/" in n for n in packed), packed
        (tmp / "data").mkdir()
        (tmp / "data" / "knowledge-base.zip").write_bytes((ROOT / "data/knowledge-base.zip").read_bytes())
        with open(tmp / "data" / "questions.csv", "w", encoding="utf8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "question"])
            w.writerows((c["id"], c["question"]) for c in cases)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        try:
            for name in args.scenarios.split(","):
                STATE.update(mode={"forced_a2": "ok", "rerank": "ok"}.get(name, name),
                             emb_calls=0, chat_calls=0, rerank_calls=0)
                extra = {"RETRIEVAL_MODE": "a2" if name == "forced_a2" else "hybrid"}
                if name == "rerank":
                    extra.update(RERANKER_MODEL="qwen/qwen3-reranker-8b", HYBRID_RERANK="1", RERANKER_TOP_N="8")
                r = run_case(tmp, port, extra)
                ok = (r["exit"] == 0 and r["rows"] == len(cases) and r["empty"] == 0
                      and r["ids"] == [c["id"] for c in cases] and EXPECT[name](r))
                r.pop("ids")
                r.update(passed=ok, emb_calls=STATE["emb_calls"], chat_calls=STATE["chat_calls"],
                         rerank_calls=STATE["rerank_calls"])
                results[name] = r
                print(f"{name:13} {'PASS' if ok else 'FAIL'} {json.dumps(r, ensure_ascii=False)}", flush=True)
        finally:
            server.shutdown()
    report = {"zip_sha256": manifest["sha256"], "zip_bytes": manifest["bytes"], "files": [f["file"] for f in manifest["files"]],
              "real_embeddings": args.real_embeddings, "questions": len(cases), "results": results}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf8")
    print("zip", manifest["bytes"], "bytes", manifest["sha256"][:16])
    sys.exit(0 if all(r["passed"] for r in results.values()) else 1)


if __name__ == "__main__":
    main()
