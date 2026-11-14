"""Locations inside the handoff package (tools/ is one level below the package root)."""
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = str(ROOT / "data" / "knowledge-base.zip")
A2 = str(ROOT / "control" / "a2.zip")
N1 = str(ROOT / "control" / "mts-energytool-n1-docs.zip")
SOURCE = str(ROOT / "source")
ALLOWED = str(ROOT / "eval" / "allowed-requirements.txt")
FRESH = str(ROOT / "eval" / "fresh_cases_v1.json")
DEV = str(ROOT / "data" / "dev123_questions.csv")
DEMO = str(ROOT / "data" / "demo_questions.csv")


def all_questions(target):
    """Demo 18 + development 123 + fresh 67 + one multi-line question, with unique ids."""
    rows = []
    for prefix, path in (("demo-", DEMO), ("", DEV)):
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows += [(prefix + r["id"], r["question"]) for r in csv.DictReader(f)]
    rows += [("fresh-" + c["id"], c["question"]) for c in json.load(open(FRESH, encoding="utf-8"))["cases"]]
    rows.append(("multi-1", "Здравствуйте!\nНужна солнечная станция 510 кВт.\nЕсть ли ограничения по мощности?"))
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "question"])
        w.writerows(rows)
    return str(target)
