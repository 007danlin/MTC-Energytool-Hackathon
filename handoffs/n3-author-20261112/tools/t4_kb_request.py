#!/usr/bin/env python3
"""The whole-base build against the confirmed N2 archive: what exactly differs in the requests (mock API, no model).

Expected: the user message is byte-identical; the system message is the N2 one with ONE inserted block
(the full texts of the remaining documents); every other field of the request is identical.

Usage: python3 tools/t4_kb_request.py <kb candidate.zip> <output directory>
"""
import glob, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario import scenario
from paths import N2, all_questions

CANDIDATE, OUT = sys.argv[1], sys.argv[2]
ALL = all_questions(Path(OUT) / "all_questions.csv")
print("candidate sha256", hashlib.sha256(open(CANDIDATE, "rb").read()).hexdigest())
print("reference sha256", hashlib.sha256(open(N2, "rb").read()).hexdigest())
a = scenario("ref", N2, ALL, OUT, keep_requests=True)
b = scenario("kb", CANDIDATE, ALL, OUT, keep_requests=True)


def load(name):
    found = {}
    for path in glob.glob(f"{OUT}/{name}/requests/*.json"):
        body = json.load(open(path, encoding="utf-8"))
        found[body["messages"][-1]["content"]] = body
    return found


ref, kb = load("ref"), load("kb")
good, blocks, sizes, ref_sizes = 0, set(), [], []
for user, body in kb.items():
    other = ref.get(user)
    if other is None:
        continue
    new, old = body["messages"][0]["content"], other["messages"][0]["content"]
    i = 0
    while i < len(old) and old[i] == new[i]:
        i += 1
    tail = old[i:]
    same_rest = {k: v for k, v in body.items() if k != "messages"} == {k: v for k, v in other.items() if k != "messages"}
    if new.endswith(tail) and same_rest and len(body["messages"]) == len(other["messages"]) == 2:
        good += 1
        blocks.add(new[i:len(new) - len(tail)])
    sizes.append(len(new) + len(user))
    ref_sizes.append(len(old) + len(user))
sizes.sort(); ref_sizes.sort()
print("rows", len(kb), "| modes", (b.get("summary") or {}).get("modes"), "| one request per row:", b["mock"]["requests"] == len(kb))
print("user messages identical to the reference:", set(kb) == set(ref))
print("system message = reference system message + one inserted block, other request fields identical:", good, "of", len(kb))
print("distinct inserted blocks:", len(blocks), "| characters:", [len(x) for x in blocks], "| starts with:", [x.strip()[:80] for x in blocks])
print("prompt characters min/median/max: candidate", sizes[0], sizes[len(sizes) // 2], sizes[-1], "| reference", ref_sizes[0], ref_sizes[len(ref_sizes) // 2], ref_sizes[-1])
ok = set(kb) == set(ref) and good == len(kb) and len(blocks) == 1
print("T4 PASS" if ok else "T4 FAIL")
sys.exit(0 if ok else 1)
