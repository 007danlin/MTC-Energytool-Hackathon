"""Build a source-backed review packet from completed diagnostic pairs only."""
import argparse
import hashlib
import json
from pathlib import Path
import random


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parent
    a.out.mkdir(parents=True, exist_ok=True)
    panel = json.loads((root / "new-panel-v1.json").read_text())
    cases = {c["id"]: c for c in panel["cases"]}
    results = {}
    for f in sorted(a.runs.glob("*/generation/result.json")):
        inp = json.loads((f.parent / "input.json").read_text())
        variant = "n2" if inp["source"].endswith("/handoff/winner/source") else "local_cap"
        result = json.loads(f.read_text())
        if result.get("answer") and not result.get("aborted"):
            results.setdefault(result["case"], {})[variant] = (result, f)
    rng = random.Random(20261113)
    packet = {"instructions": "Evaluate factual claims against the supplied sources and full dialogue. Do not reward length. Identify new false claims even in already-wrong answers. Return A/B/tie/uncertain and concrete evidence for each pair. This is a small local diagnostic, not platform Score.",
              "pairs": []}
    mapping = {"pairs": [], "incomplete": []}
    for case_id in ("np01", "np03", "np09", "np11"):
        variants = results.get(case_id, {})
        if set(variants) != {"n2", "local_cap"}:
            mapping["incomplete"].append(case_id)
            continue
        order = ["n2", "local_cap"]
        rng.shuffle(order)
        c = cases[case_id]
        row = {k: c[k] for k in ("id", "question", "required_claims", "forbidden_claims", "evidence")}
        row["answers"] = {label: variants[variant][0]["answer"] for label, variant in zip(("A", "B"), order)}
        packet["pairs"].append(row)
        mapping["pairs"].append({"id": case_id, "labels": dict(zip(("A", "B"), order)),
                                 "artifacts": {variant: {"path": str(f), "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                                                           "runtime_info": result.get("info")}
                                               for variant, (result, f) in variants.items()}})
    (a.out / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    (a.out / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"completed_pairs": len(packet["pairs"]), "incomplete": mapping["incomplete"]}))


if __name__ == "__main__":
    main()
