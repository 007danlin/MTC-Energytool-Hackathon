"""Local retrieval experiment: BM25 (current) vs bge-m3 dense vs hybrid (RRF).

Private diagnostic; never part of the submission ZIP. Runs with the local .venv
(sentence-transformers + BAAI/bge-m3 on CPU). On the platform the same embeddings
would come from POST {LLM_BASE_URL}/embeddings.

Usage:
  .venv/Scripts/python tools/dense_benchmark.py --output reports/private/dense-v1.json
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from dialogue import parse_question, retrieval_query  # noqa: E402
from retrieval import LexicalRetriever, load_fragments  # noqa: E402

TOP = 12


def dense_query(messages):
    """Current user turn first, then earlier user turns (assistant turns carry no client facts)."""
    users = [m.content for m in messages if m.role == "user"]
    return " \n".join([users[-1]] + users[-2::-1][:2])


def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for pos, sid in enumerate(ranking):
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + pos + 1)
    return [sid for sid, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def evaluate(cases, ranked):
    rows = {"dev": [], "holdout": []}
    for case in cases:
        ids = ranked[case["id"]]
        ranks = [min((ids.index(s) + 1 for s in grp if s in ids), default=None) for grp in case["groups"]]
        rows[case["split"]].extend(ranks)
    out = {}
    for split, ranks in rows.items():
        if not ranks:
            continue
        cov = lambda k: round(sum(r is not None and r <= k for r in ranks) / len(ranks), 3)
        out[split] = {"facts": len(ranks), "@1": cov(1), "@3": cov(3), "@6": cov(6), "@12": cov(12),
                      "MRR": round(statistics.mean(1 / r if r else 0 for r in ranks), 3)}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kb", default=str(ROOT / "data/knowledge-base.zip"))
    p.add_argument("--cases", default=str(ROOT / "data/eval/retrieval_cases_v2.json"))
    p.add_argument("--model", default="BAAI/bge-m3")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    from sentence_transformers import SentenceTransformer

    cases = json.loads(Path(args.cases).read_text(encoding="utf8"))
    fragments = load_fragments(args.kb)
    sids = [f.source_id for f in fragments]
    bm25 = LexicalRetriever(fragments)

    t0 = time.time()
    model = SentenceTransformer(args.model, device="cpu")
    load_s = time.time() - t0
    t0 = time.time()
    doc_vecs = model.encode([f.text for f in fragments], batch_size=8, normalize_embeddings=True,
                            show_progress_bar=False)
    index_s = time.time() - t0

    ranked = {"bm25_full": {}, "bm25_core": {}, "dense": {}, "hybrid_rrf": {}}
    q_times = []
    for case in cases:
        messages = parse_question(case["question"])
        full = [f.source_id for f in bm25.search(retrieval_query(messages), TOP)]
        # bm25 "core" = only the ranked top-k, without companion guard/support fragments.
        core = full[:TOP]
        t0 = time.time()
        qv = model.encode([dense_query(messages)], normalize_embeddings=True, show_progress_bar=False)[0]
        q_times.append(time.time() - t0)
        order = np.argsort(-(doc_vecs @ qv))
        dense = [sids[i] for i in order[:50]]
        ranked["bm25_full"][case["id"]] = full
        ranked["bm25_core"][case["id"]] = core
        ranked["dense"][case["id"]] = dense
        ranked["hybrid_rrf"][case["id"]] = rrf([core, dense[:30]])

    summary = {name: evaluate(cases, r) for name, r in ranked.items()}
    report = {"summary": summary,
              "timing_s": {"model_load": round(load_s, 1), "index_234_fragments": round(index_s, 1),
                           "query_mean": round(statistics.mean(q_times), 3)},
              "note": "bm25_full includes companion fragments beyond top-12; others are pure top-k",
              "ranked": ranked}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf8")
    for name, s in summary.items():
        print(f"{name:11}", json.dumps(s.get("dev"), ensure_ascii=False))
    print("timing", report["timing_s"])


if __name__ == "__main__":
    main()
