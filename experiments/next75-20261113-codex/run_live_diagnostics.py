"""Run the predeclared four pairs, serially, through the exact HTTP recorder.

No platform upload or remote inference. Each row is a diagnostic with a fresh
budget; the manifest explicitly distinguishes this from a full batch test.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--upstream", default="http://127.0.0.1:18765")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--budget-seconds", type=float, default=3600)
    a = p.parse_args()
    root = Path(__file__).resolve().parent
    a.out.mkdir(parents=True, exist_ok=False)
    sources = {"n2": root / "handoff/winner/source", "local_cap": a.candidate.resolve()}
    ordered = [(case, variant) for i, case in enumerate(("np01", "np03", "np09", "np11"))
               for variant in (("n2", "local_cap") if i % 2 == 0 else ("local_cap", "n2"))]
    manifest = {"kind": "paired-local-generations-after-synthetic-refusal",
                "not_platform_batch": True, "model": a.model, "ordered_runs": ordered,
                "diagnostic_wall_budget_seconds": a.budget_seconds,
                "started_unix": time.time(), "completed": []}
    wall_deadline = time.monotonic() + a.budget_seconds
    mf = a.out / "manifest.json"
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for number, (case, variant) in enumerate(ordered, 1):
        if time.monotonic() >= wall_deadline:
            manifest["stopped_reason"] = "diagnostic_wall_budget"
            mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            break
        run = a.out / ("%02d-%s-%s" % (number, case, variant))
        run.mkdir()
        proxy_log = (run / "proxy.log").open("w")
        proxy = subprocess.Popen([sys.executable, str(root / "http_trace_proxy.py"), "--upstream", a.upstream,
                                  "--out", str(run / "http")], stdout=proxy_log, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if (run / "http/port.txt").exists():
                    break
                if proxy.poll() is not None:
                    raise RuntimeError("HTTP recorder did not start")
                time.sleep(.05)
            port = (run / "http/port.txt").read_text().strip()
            cmd = [sys.executable, str(root / "generate_diagnostic_case.py"),
                   "--source", str(sources[variant]), "--panel", str(root / "new-panel-v1.json"),
                   "--case", case, "--kb", str(root / "n2-test-reference/data/knowledge-base.zip"),
                   "--model", a.model, "--base-url", "http://127.0.0.1:" + port + "/v1",
                   "--out", str(run / "generation"), "--seed-overflow"]
            started = time.monotonic()
            print(json.dumps({"event": "start", "run": number, "case": case, "variant": variant}), flush=True)
            with (run / "stdout.log").open("w") as stdout, (run / "stderr.log").open("w") as stderr:
                generation = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
                try:
                    status = {"exit_code": generation.wait(timeout=min(1250, max(1, wall_deadline-time.monotonic())))}
                except subprocess.TimeoutExpired:
                    status = {"timeout": True}
                finally:
                    if generation.poll() is None:
                        generation.kill()
                        generation.wait()
            status.update(run=number, case=case, variant=variant, elapsed_seconds=time.monotonic() - started)
            (run / "runner-result.json").write_text(json.dumps(status, indent=2) + "\n")
            manifest["completed"].append(status)
            mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"event": "done", **status}), flush=True)
            if status.get("exit_code") != 0:
                print("Stopping after failed case; incomplete pairs are preserved.", flush=True)
                break
        finally:
            for _ in range(20):
                pending = [f for f in (run / "http").glob("*.metadata.json")
                           if json.loads(f.read_text()).get("state") == "started"]
                if not pending:
                    break
                time.sleep(.05)
            proxy.terminate()
            proxy.wait(timeout=10)
            proxy_log.close()
            for f in (run / "http").glob("*.metadata.json"):
                item = json.loads(f.read_text())
                if item.get("state") == "started":
                    item.update(state="recorder_terminated", upstream_completion_unknown=True)
                    f.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
