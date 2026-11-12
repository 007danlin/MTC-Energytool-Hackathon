#!/usr/bin/env python3
"""Start the mock API with given options, run a ZIP through run_zip.py, return combined report."""
import json, os, subprocess, sys, tempfile, time, urllib.request, shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paths import KB


def scenario(name, zip_path, questions, out_root, mock=(), env=(), python=sys.executable, base_var="LLM_BASE_URL", timeout=1300, keep_requests=False):
    out = Path(out_root) / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rec = out / "requests"
    port_file = out / "port"
    server = subprocess.Popen([sys.executable, str(HERE / "mock_api.py"), "--record", str(rec), "--port-file", str(port_file), *mock],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.05)
        port = int(port_file.read_text())
        cmd = [sys.executable, str(HERE / "run_zip.py"), "--zip", zip_path, "--questions", questions, "--kb", KB,
               "--base-url", f"http://127.0.0.1:{port}/v1", "--output", str(out), "--python", python,
               "--base-var", base_var, "--timeout", str(timeout)]
        for e in env:
            cmd += ["--env", e]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        stats = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/__stats", timeout=10).read())
    finally:
        server.terminate()
        server.wait(timeout=10)
    report = json.loads((out / "report.json").read_text()) if (out / "report.json").exists() else {"error": proc.stderr[-2000:]}
    report["mock"] = {"requests": stats["count"],
                      "kinds": {k: sum(1 for e in stats["log"] if e.get("kind") == k) for k in sorted({e.get("kind") for e in stats["log"]})},
                      "auth_ok": all(e["auth_ok"] for e in stats["log"]) if stats["log"] else None,
                      "models": sorted({str(e.get("model")) for e in stats["log"]}),
                      "max_tokens": sorted({e.get("max_tokens") for e in stats["log"] if e.get("max_tokens") is not None}),
                      "extras": sorted({",".join(e.get("extra", [])) for e in stats["log"]}),
                      "temperatures": sorted({e.get("temperature") for e in stats["log"] if e.get("temperature") is not None}),
                      "top_p": sorted({e.get("top_p") for e in stats["log"] if e.get("top_p") is not None}),
                      "ok_by_tokens": {str(k): sum(1 for e in stats["log"] if e.get("kind") == "ok" and e.get("max_tokens") == k)
                                       for k in sorted({e.get("max_tokens") for e in stats["log"] if e.get("max_tokens") is not None})},
                      "prompt_chars_max": max((e.get("prompt_chars", 0) for e in stats["log"]), default=0),
                      "body_hashes": sorted(e["sha256"] for e in stats["log"] if e.get("kind") != "auth")}
    (out / "scenario.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if not keep_requests:
        shutil.rmtree(rec, ignore_errors=True)
    return report
