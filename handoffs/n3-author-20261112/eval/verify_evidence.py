#!/usr/bin/env python3
"""Check the frozen fresh set: file hashes and that every evidence quote is literally in the knowledge base.

Usage: python3 eval/verify_evidence.py [path to the organizers' written Q&A .md]
"""
import hashlib, json, re, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parent / "stand" / "data" / "knowledge-base.zip"


def norm(s):
    s = re.sub(r"[ \t]*-{3,}[ \t-]*", " ", s.replace(" ", " "))
    return re.sub(r"\s+", " ", s).strip().lower().replace("ё", "е")


frozen = json.loads((HERE / "FROZEN.json").read_text())
problems = []
for name in ("fresh_cases_v1.json", "fresh_questions_v1.csv"):
    if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != frozen[name]:
        problems.append("hash mismatch: " + name)
data = json.loads((HERE / "fresh_cases_v1.json").read_text(encoding="utf-8"))
if hashlib.sha256(KB.read_bytes()).hexdigest() != data["kb_sha256"]:
    problems.append("knowledge base differs from the one used for the goldens")
archive = zipfile.ZipFile(KB)
kb = {n: norm(archive.read(n).decode("utf-8-sig")) for n in archive.namelist()}
qa = norm(Path(sys.argv[1]).read_text(encoding="utf-8").replace("\\", "")) if len(sys.argv) > 1 else None
checked = skipped = 0
for case in data["cases"]:
    for e in case["evidence"]:
        if e["file"] == "organizers-qa":
            if qa is None:
                skipped += 1
            elif norm(e["quote"]) not in qa:
                problems.append("Q&A quote not found: %s" % case["id"])
            else:
                checked += 1
        elif norm(e["quote"]) not in kb.get(e["file"], ""):
            problems.append("KB quote not found: %s %s" % (case["id"], e["file"]))
        else:
            checked += 1
print(json.dumps({"cases": len(data["cases"]), "quotes_verified": checked, "organizer_qa_quotes_skipped": skipped,
                  "frozen_at": frozen["frozen_at_msk"], "problems": problems}, ensure_ascii=False, indent=1))
sys.exit(1 if problems else 0)
