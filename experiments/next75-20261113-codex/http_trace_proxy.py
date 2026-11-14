"""Local-only HTTP boundary recorder for paired inference experiments.

Request bodies are preserved exactly; authorization headers are never logged.
This tool is an experiment harness, not a submission module.
"""
import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    upstream = urlsplit(args.upstream)
    if upstream.scheme != "http" or upstream.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Only a local HTTP inference server is allowed")
    args.out.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    sequence = 0

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *unused):
            pass

        def do_POST(self):
            nonlocal sequence
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with lock:
                sequence += 1
                attempt = sequence
            stem = args.out / ("%05d" % attempt)
            stem.with_suffix(".request.bin").write_bytes(body)
            parsed = json.loads(body)
            record = {
                "attempt": attempt, "started_unix": time.time(), "path": self.path,
                "state": "started",
                "request_sha256": hashlib.sha256(body).hexdigest(),
                "request_bytes": len(body), "model": parsed.get("model"),
                "parameters": {k: v for k, v in parsed.items() if k != "messages"},
                "prompt_chars": sum(len(m.get("content", "")) for m in parsed.get("messages", [])),
            }
            def save_record():
                temporary = stem.with_suffix(".metadata.json.tmp")
                temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
                temporary.replace(stem.with_suffix(".metadata.json"))
            save_record()
            start = time.monotonic()
            conn = http.client.HTTPConnection(upstream.hostname, upstream.port, timeout=1800)
            sent_headers = False
            try:
                headers = {"Content-Type": "application/json"}
                # Forward authorization if present but never write its value to disk.
                if self.headers.get("Authorization"):
                    headers["Authorization"] = self.headers["Authorization"]
                conn.request("POST", upstream.path.rstrip("/") + self.path, body=body, headers=headers)
                response = conn.getresponse()
                result = response.read()
                record["http_status"] = response.status
                stem.with_suffix(".response.bin").write_bytes(result)
                record["response_sha256"] = hashlib.sha256(result).hexdigest()
                try:
                    decoded = json.loads(result)
                    record["usage"] = decoded.get("usage")
                    record["choices"] = [{"finish_reason": c.get("finish_reason"),
                                           "content_chars": len((c.get("message") or {}).get("content") or ""),
                                           "reasoning_chars": len((c.get("message") or {}).get("reasoning_content") or (c.get("message") or {}).get("reasoning") or "")}
                                          for c in decoded.get("choices", [])]
                    if "error" in decoded:
                        record["error"] = decoded["error"]
                except Exception as exc:
                    # Metadata must never change the original status or body.
                    record["metadata_parse_error"] = type(exc).__name__
                self.send_response(response.status)
                hop_headers = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
                               "te", "trailer", "transfer-encoding", "upgrade", "content-length"}
                for name, value in response.getheaders():
                    if name.lower() not in hop_headers:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(result)))
                self.end_headers()
                sent_headers = True
                self.wfile.write(result)
            except Exception as exc:
                record["transport_error"] = type(exc).__name__ + ": " + str(exc)
                try:
                    if not sent_headers:
                        self.send_error(502, "Local upstream transport failure")
                except OSError:
                    pass
            finally:
                conn.close()
                record["state"] = "finished"
                record["elapsed_seconds"] = round(time.monotonic() - start, 6)
                save_record()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    (args.out / "port.txt").write_text(str(server.server_address[1]))
    print(json.dumps({"port": server.server_address[1], "out": str(args.out)}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
