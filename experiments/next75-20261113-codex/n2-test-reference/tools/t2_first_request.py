#!/usr/bin/env python3
"""In normal conditions the candidate must send the same requests as the scored N1 archive (first request of every row).

Usage: t2_first_request.py CANDIDATE.zip OUT_DIR [NAME=VALUE ...]   (extra environment for the candidate only)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario import scenario
from paths import N1, all_questions

CANDIDATE, OUT, extra = sys.argv[1], sys.argv[2], sys.argv[3:]
questions = all_questions(Path(OUT) / "all_questions.csv")
a = scenario("n1", N1, questions, OUT)
b = scenario("candidate", CANDIDATE, questions, OUT, env=extra)
same_req = a["mock"]["body_hashes"] == b["mock"]["body_hashes"]
same_csv = a["csv"]["sha256"] == b["csv"]["sha256"]
print("rows", a["csv"]["rows"], b["csv"]["rows"], "requests", a["mock"]["requests"], b["mock"]["requests"],
      "identical request bodies:", same_req, "identical csv:", same_csv)
print("T2 PASS" if same_req and same_csv else "T2 FAIL")
sys.exit(0 if same_req and same_csv else 1)
