#!/usr/bin/env python3
"""Candidate against the confirmed N2 archive on the mock API (no language model).

1. IDENTITY: on an ordinary run the candidate must send byte-identical requests and write an identical CSV,
   under four sets of platform variables.
2. A1-A4: service failures where the two archives are expected to differ.

Usage: python3 tools/t3_compare.py <candidate.zip> <output directory>
"""
import hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario import scenario
from paths import N2, all_questions

CANDIDATE, OUT = sys.argv[1], sys.argv[2]
ALL = all_questions(Path(OUT) / "all_questions.csv")
print("candidate sha256", hashlib.sha256(open(CANDIDATE, "rb").read()).hexdigest())
print("reference sha256", hashlib.sha256(open(N2, "rb").read()).hexdigest())


def show(name, r):
    sm = r.get("summary") or {}
    print(name, "| exit", r.get("exit_code"), "| csv", {k: r["csv"][k] for k in ("rows", "problems", "technical_stubs")} if r.get("csv") else r.get("error"),
          "| requests", r["mock"]["requests"], r["mock"]["kinds"], "| answered by max_tokens", r["mock"]["ok_by_tokens"],
          "| seconds", r.get("elapsed_seconds"),
          "| summary", {k: sm.get(k) for k in ("statuses", "modes", "context_at_end", "window_chars", "workers_at_end", "fast_mode")}, flush=True)


ok = True
for label, env in (("default", []), ("env-a", ["TOP_K=4", "MAX_TOKENS=1024", "TEMPERATURE=0.2", "MAX_WORKERS=5"]),
                   ("env-b", ["TOP_K=20", "MAX_TOKENS=8192", "MAX_WORKERS=8"]), ("env-c", ["MAX_TOKENS=4096", "MAX_WORKERS=1", "TEMPERATURE=0.7"])):
    a = scenario("ref-" + label, N2, ALL, OUT, env=env)
    b = scenario("new-" + label, CANDIDATE, ALL, OUT, env=env)
    same = a["mock"]["body_hashes"] == b["mock"]["body_hashes"]
    same_csv = a["csv"]["sha256"] == b["csv"]["sha256"]
    ok &= same and same_csv
    print("IDENTITY", label, "| requests", a["mock"]["requests"], b["mock"]["requests"], "| identical request bodies:", same,
          "| identical csv:", same_csv, "| max_tokens", a["mock"]["max_tokens"], "| temperature", a["mock"]["temperatures"], flush=True)
print("IDENTITY", "PASS" if ok else "FAIL (expected for a build that changes the requests, e.g. context=kb)")

cold = ["--delay", "0.3", "--slow-over", "60000", "--slow-delay", "8", "--slow-until", "10"]
show("A1 reference | cold start: large prompts slow for the first 10 s", scenario("ref-cold", N2, ALL, OUT, mock=cold, env=["N1_BIG_TIMEOUT=5"]))
show("A1 candidate | cold start: large prompts slow for the first 10 s", scenario("new-cold", CANDIDATE, ALL, OUT, mock=cold, env=["N1_BIG_TIMEOUT=5", "N3_PROBE_SECONDS=2"]))
show("A2 reference | one refusal 'max_tokens is too large ... N input tokens'", scenario("ref-sum", N2, ALL, OUT, mock=["--context-limit", "100000", "--context-sum"]))
show("A2 candidate | one refusal 'max_tokens is too large ... N input tokens'", scenario("new-sum", CANDIDATE, ALL, OUT, mock=["--context-limit", "100000", "--context-sum"]))
show("A3 reference | 30 rate-limit answers at start", scenario("ref-429", N2, ALL, OUT, mock=["--fail-first", "30", "--fail-status", "429"]))
show("A3 candidate | 30 rate-limit answers at start", scenario("new-429", CANDIDATE, ALL, OUT, mock=["--fail-first", "30", "--fail-status", "429"]))
show("A4 candidate | large prompts always slow (bounded tries to return)", scenario("new-slow", CANDIDATE, ALL, OUT, mock=["--delay", "0.2", "--slow-over", "60000", "--slow-delay", "8"], env=["N1_BIG_TIMEOUT=5", "N3_PROBE_SECONDS=2"]))
