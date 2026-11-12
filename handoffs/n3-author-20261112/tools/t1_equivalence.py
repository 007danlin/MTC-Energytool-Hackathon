#!/usr/bin/env python3
"""The candidate in control mode (N1_CONTROL=1) must send byte-identical requests to the real A2 archive."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario import scenario
from paths import A2, all_questions

CANDIDATE, OUT = sys.argv[1], sys.argv[2]
questions = all_questions(Path(OUT) / "all_questions.csv")
ok = True
for label, env in (("envdefault", []), ("topk4", ["TOP_K=4", "MAX_TOKENS=1024", "TEMPERATURE=0.2", "MAX_WORKERS=5"]), ("topk20", ["TOP_K=20", "MAX_TOKENS=4096"])):
    a = scenario("a2-" + label, A2, questions, OUT, env=env)
    n = scenario("ctl-" + label, CANDIDATE, questions, OUT, env=env + ["N1_CONTROL=1"])
    same_req = a["mock"]["body_hashes"] == n["mock"]["body_hashes"]
    same_csv = a["csv"]["sha256"] == n["csv"]["sha256"]
    print(label, "rows", a["csv"]["rows"], n["csv"]["rows"], "requests", a["mock"]["requests"], n["mock"]["requests"],
          "identical request bodies:", same_req, "identical csv:", same_csv, "max_tokens", a["mock"]["max_tokens"], n["mock"]["max_tokens"])
    ok &= same_req and same_csv
print("T1 PASS" if ok else "T1 FAIL")
sys.exit(0 if ok else 1)
