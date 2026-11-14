"""One real local-model case after an explicitly synthetic context-refusal prefix.

The two synthetic exchanges isolate the persistent output-cap state. They are
not model answers and are stored separately from the real HTTP trace.
"""
import argparse
from dataclasses import asdict
import hashlib
import http.client
import json
from pathlib import Path
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--kb", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed-overflow", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(a.source.resolve()))
    from settings import Settings
    from llm_client import LLMClient, HTTPTransport
    from consultant import Consultant

    class DiagnosticAbort(BaseException):
        pass

    class DiagnosticTransport(HTTPTransport):
        def post(self, *args, **kwargs):
            try:
                return super().post(*args, **kwargs)
            except (OSError, TimeoutError, http.client.HTTPException) as exc:
                # A timed-out local inference may still be running. End this
                # diagnostic instead of overlapping another long GPU request.
                raise DiagnosticAbort(type(exc).__name__) from None

    cases = json.loads(a.panel.read_text())["cases"]
    case = next(c for c in cases if c["id"] == a.case)
    env = {"LLM_BASE_URL": a.base_url, "LLM_API_KEY": "local-diagnostic-only",
           "LLM_MODEL": a.model, "MAX_WORKERS": "1", "LLM_TIMEOUT": "900",
           "N1_BIG_TIMEOUT": "900", "RUN_BUDGET_SECONDS": "1120"}
    settings = Settings.from_env(env)
    client = LLMClient(settings, transport=DiagnosticTransport())
    seed = []
    if a.seed_overflow:
        class SyntheticPrefix:
            def post(self, url, headers, payload, timeout):
                seed.append({"sha256": hashlib.sha256(payload).hexdigest(),
                             "payload": json.loads(payload), "synthetic": True})
                if len(seed) == 1:
                    return 400, {}, json.dumps({"error": {"message":
                        "max_tokens is too large: maximum context length is 32768 tokens "
                        "and your request has 30000 input tokens"}}).encode()
                return 200, {}, json.dumps({"choices": [{"message": {"content": "Synthetic seed only"},
                                                          "finish_reason": "stop"}]}).encode()
        client.transport = SyntheticPrefix()
        client.chat([{"role": "user", "content": "Synthetic state seed; no model is called."}],
                    max_tokens=settings.main_max_tokens)
        client.transport = DiagnosticTransport()
    (a.out / "synthetic-prefix.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n")
    config = asdict(settings)
    config.pop("api_key")
    before = {"source": str(a.source.resolve()),
              "source_hashes": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                                for f in sorted(a.source.glob("*.py"))},
              "case": a.case, "question": case["question"], "settings": config,
              "panel_sha256": hashlib.sha256(a.panel.read_bytes()).hexdigest(),
              "kb_sha256": hashlib.sha256(a.kb.read_bytes()).hexdigest(),
              "synthetic_prefix": a.seed_overflow,
              "initial_output_cap": client._max_tokens_cap,
              "caveat": "Diagnostic row with its own 1120-second budget; not a full platform batch.",
              "started_unix": time.time()}
    (a.out / "input.json").write_text(json.dumps(before, ensure_ascii=False, indent=2) + "\n")
    consultant = Consultant(client, a.kb, settings)
    started = time.monotonic()
    try:
        answer, info = consultant.answer(case["question"], deadline=started + settings.runtime_seconds)
    except DiagnosticAbort as exc:
        aborted = {"case": a.case, "aborted": True, "reason": str(exc),
                   "elapsed_seconds": time.monotonic() - started,
                   "caveat": "Diagnostic stopped after transport failure to prevent overlapping local inference; not an N2 recovery result."}
        (a.out / "result.json").write_text(json.dumps(aborted, indent=2) + "\n")
        print(json.dumps(aborted), flush=True)
        raise SystemExit(3)
    result = {"case": a.case, "answer": answer, "info": info,
              "elapsed_seconds": time.monotonic() - started,
              "final_output_cap": client._max_tokens_cap,
              "real_http_calls": client.calls - len(seed),
              "final_context_mode": consultant.state.mode(),
              "final_allowed_chars": consultant.state.allowed_chars()}
    (a.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
