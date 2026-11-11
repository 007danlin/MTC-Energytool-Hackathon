"""Evidence completeness of the final context: A2 (A) vs hybrid (B) vs hybrid+rerank (C).

Private diagnostic (local models, not part of the ZIP). Uses eval/cases_v3.json.
Local stand-ins for platform services: BAAI/bge-m3 via sentence-transformers and,
with --rerank, Qwen/Qwen3-Reranker-0.6B (the platform offers the 8B model).

  .venv/Scripts/python tools/evidence_benchmark.py --output reports/private/evidence-v3.json [--rerank]
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dialogue import parse_question, retrieval_query  # noqa: E402
from hybrid_retrieval import HybridRetriever  # noqa: E402
from retrieval import LexicalRetriever, load_fragments  # noqa: E402


class LocalModels:
    """embed()/rerank() with the same semantics as hybrid_retrieval.APIEmbedder."""

    def __init__(self, rerank_model=None, max_len=1024):
        self.max_len = max_len
        from sentence_transformers import SentenceTransformer
        self.st = SentenceTransformer("BAAI/bge-m3", device="cpu")
        self.reranker = None
        self._cache = {}
        if rerank_model:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self.torch = torch
            self.tok = AutoTokenizer.from_pretrained(rerank_model, padding_side="left")
            self.reranker = AutoModelForCausalLM.from_pretrained(rerank_model).eval()
            self.yes = self.tok.convert_tokens_to_ids("yes")
            self.no = self.tok.convert_tokens_to_ids("no")
            self.prefix = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
                           "and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n"
                           "<|im_start|>user\n")
            self.suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def embed(self, texts, *, query=False):
        return [list(map(float, v)) for v in self.st.encode(texts, batch_size=8, normalize_embeddings=True,
                                                             show_progress_bar=False)]

    def rerank(self, query, documents, top_n):
        # Same pool for C6/C8/C12: score once, slice per variant.
        key = (query, tuple(documents))
        if key not in self._cache:
            self._cache[key] = self._rerank_order(query, documents)
        return self._cache[key][:top_n]

    def _rerank_order(self, query, documents):
        task = "Given a web search query, retrieve relevant passages that answer the query"
        pairs = [self.prefix + f"<Instruct>: {task}\n<Query>: {query}\n<Document>: {d[:2000]}" + self.suffix
                 for d in documents]
        scores = []
        with self.torch.no_grad():
            for i in range(0, len(pairs), 4):
                batch = self.tok(pairs[i:i + 4], padding=True, truncation=True, max_length=self.max_len, return_tensors="pt")
                logits = self.reranker(**batch).logits[:, -1, :]
                two = self.torch.stack([logits[:, self.no], logits[:, self.yes]], dim=1)
                scores.extend(self.torch.softmax(two, dim=1)[:, 1].tolist())
        return sorted(range(len(documents)), key=lambda i: -scores[i])


def case_docs(case):
    items = case["required_facts"] + case["conditional_facts"] + case["forbidden_claims"]
    return {s["source_id"].split("#")[0] for it in items for s in it["sources"]}


def score_case(case, ids, chars_by_id, primary):
    present = set(ids)
    req = [any(s["source_id"] in present for s in f["sources"]) for f in case["required_facts"]]
    cond = [any(s["source_id"] in present for s in f["sources"]) for f in case["conditional_facts"]]
    rules = [any(s["source_id"] in present for s in c["sources"]) for c in case["forbidden_claims"] if c["sources"]]
    docs = case_docs(case)
    total = sum(chars_by_id[i] for i in ids)
    irrelevant = sum(chars_by_id[i] for i in ids if i.split("#")[0] not in docs)
    ranks = [min((primary.index(s["source_id"]) + 1 for s in f["sources"] if s["source_id"] in primary), default=None)
             for f in case["required_facts"]]
    return {"all_required": all(req) if req else None, "required_hits": req, "conditional_hits": cond,
            "rule_hits": rules, "chars": total, "fragments": len(ids),
            "irrelevant_share": round(irrelevant / total, 3) if total else 0.0, "primary_ranks": ranks}


def aggregate(rows):
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.mean(xs), 3) if xs else None
    facts = [h for r in rows for h in r["required_hits"]]
    ranks = [x for r in rows for x in r["primary_ranks"]]
    cov = lambda k: round(sum(x is not None and x <= k for x in ranks) / len(ranks), 3) if ranks else None
    return {"cases": len(rows),
            "all_required_rate": mean([float(r["all_required"]) for r in rows if r["all_required"] is not None]),
            "required_fact_rate": mean([float(h) for h in facts]),
            "conditional_rate": mean([float(h) for r in rows for h in r["conditional_hits"]]),
            "rule_coverage": mean([float(h) for r in rows for h in r["rule_hits"]]),
            "primary@6": cov(6), "primary@12": cov(12),
            "chars_median": statistics.median(r["chars"] for r in rows),
            "chars_p95": sorted(r["chars"] for r in rows)[max(0, int(len(rows) * .95) - 1)],
            "fragments_mean": mean([r["fragments"] for r in rows]),
            "irrelevant_share_mean": mean([r["irrelevant_share"] for r in rows]),
            "search_ms_mean": mean([r["ms"] for r in rows])}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kb", default=str(ROOT / "data/knowledge-base.zip"))
    p.add_argument("--cases", default=str(ROOT / "eval/cases_v3.json"))
    p.add_argument("--rerank", action="store_true")
    p.add_argument("--rerank-model", default="Qwen/Qwen3-Reranker-0.6B")
    p.add_argument("--rerank-pool", type=int, default=20)
    p.add_argument("--rerank-max-len", type=int, default=1024)
    p.add_argument("--variants", default="", help="comma list to run (default: all)")
    p.add_argument("--split", default="all", help="dev | holdout | all")
    p.add_argument("--limit", type=int, default=0, help="first N cases after split filter")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf8"))["cases"]
    if args.split != "all":
        cases = [c for c in cases if c["split"] == args.split]
    if args.limit:
        cases = cases[:args.limit]
    fragments = load_fragments(args.kb)
    chars_by_id = {f.source_id: len(f.text) for f in fragments}
    models = LocalModels(args.rerank_model if args.rerank else None, max_len=args.rerank_max_len)
    t0 = time.time()
    variants = {"A_a2": LexicalRetriever(fragments)}
    hybrid = HybridRetriever(fragments, models)
    index_s = round(time.time() - t0, 1)
    plain = HybridRetriever(fragments, models, disabled=True, general_rules=False)
    plain.vectors, plain.stats["mode"] = hybrid.vectors, "hybrid"
    variants["B_top12_norules"] = (plain, 12)
    variants["B_top12"] = (hybrid, 12)
    variants["B_top8"] = (hybrid, 8)
    variants["B_top6"] = (hybrid, 6)
    if args.rerank:
        for name, n in (("C_rerank8", 8), ("C_rerank6", 6), ("C_rerank12", 12)):
            c = HybridRetriever(fragments, models, rerank=True, rerank_top_n=n, disabled=True,
                                rerank_pool=args.rerank_pool)
            c.vectors, c.stats["mode"] = hybrid.vectors, "hybrid"  # identical index; avoid re-encoding
            variants[name] = (c, n)

    if args.variants:
        keep = set(args.variants.split(","))
        variants = {k: v for k, v in variants.items() if k in keep or k == "A_a2"}
    raw, summary = {}, {}
    for name, spec in variants.items():
        retriever, top_k = (spec, 12) if not isinstance(spec, tuple) else spec
        rows = {}
        for case in cases:
            query = retrieval_query(parse_question(case["question"]))
            started = time.time()
            found = retriever.search(query, top_k)
            ms = (time.time() - started) * 1000
            ids = [f.source_id for f in found]
            primary = (retriever.ranked_ids(query, top_k)[0][:12] if isinstance(retriever, HybridRetriever)
                       else [f.source_id for f in found if f.score > 0][:12])
            row = score_case(case, ids, chars_by_id, primary)
            row.update(ms=round(ms, 1), sources=ids)
            rows[case["id"]] = row
            if name.startswith("C_") and len(rows) % 5 == 0:
                print(f"[{time.strftime('%H:%M:%S')}] {name} {len(rows)}/{len(cases)}", flush=True)
        raw[name] = rows
        print(f"[{time.strftime('%H:%M:%S')}] {name} done", flush=True)
        groups = defaultdict(list)
        for case in cases:
            r = rows[case["id"]]
            groups[case["split"]].append(r)
            if case["split"] == "dev":
                groups["dev:" + case["topic"]].append(r)
                groups["dev:type:" + case["type"]].append(r)
        summary[name] = {g: aggregate(rs) for g, rs in sorted(groups.items())}
        if isinstance(retriever, HybridRetriever):
            summary[name]["retriever_stats"] = dict(retriever.stats)

    # Worst cases: required facts present in A but lost in a candidate (dev only).
    losses = {}
    for name in variants:
        if name == "A_a2":
            continue
        losses[name] = [c["id"] for c in cases if c["split"] == "dev" and any(
            a and not b for a, b in zip(raw["A_a2"][c["id"]]["required_hits"], raw[name][c["id"]]["required_hits"]))]
    report = {"cases_file": args.cases, "index_seconds": index_s, "summary": summary,
              "lost_vs_A": losses, "raw": raw}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf8")
    keys = ("all_required_rate", "required_fact_rate", "conditional_rate", "rule_coverage", "primary@6",
            "chars_median", "fragments_mean", "irrelevant_share_mean", "search_ms_mean")
    print("dev:", *keys, sep="\t")
    for name in variants:
        print(name, *(summary[name]["dev"][k] for k in keys), sep="\t")
    print("holdout:")
    for name in variants:
        print(name, *(summary[name]["holdout"][k] for k in keys[:5]), sep="\t")
    print("lost vs A (dev):", {k: v for k, v in losses.items()})


if __name__ == "__main__":
    main()
