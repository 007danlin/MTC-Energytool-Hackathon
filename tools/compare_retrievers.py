"""Same A2 generation, different retrieval: raw answers + blinded pairs for review.

For Daniel's local model (OpenAI-compatible env: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL).
Prompt, max_tokens, model and questions are identical across variants; only the
Retriever object differs. Embeddings: the local proxy (/embeddings, EMB_MODEL) or,
with --local-embeddings, BAAI/bge-m3 via sentence-transformers.

  python tools/compare_retrievers.py --variants A,B --split dev --output reports/private/a3-compare
  python tools/compare_retrievers.py --variants A,B --cases my_final_cases.json --output ...

Writes <output>/answers.json (raw answers, sources, timing, API errors per variant)
and <output>/blind_pairs.json + blind_key.json (shuffled order; key kept separate).
"""
import argparse
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consultant import Consultant  # noqa: E402
from contracts import ConsultationRequest  # noqa: E402
from dialogue import parse_question  # noqa: E402
from hybrid_retrieval import APIEmbedder, HybridRetriever  # noqa: E402
from llm_client import LLMClient  # noqa: E402
from retrieval import LexicalRetriever, load_fragments  # noqa: E402
from settings import Settings, env_first  # noqa: E402


def make_variants(names, fragments, settings, local):
    if local:
        sys.path.insert(0, str(ROOT / "tools"))
        from evidence_benchmark import LocalModels
        embedder = LocalModels()
    else:
        embedder = APIEmbedder(settings.base_url, settings.api_key, env_first("EMB_MODEL", default="baai/bge-m3"),
                               rerank_model=env_first("RERANKER_MODEL") or None)
    out = {}
    hybrid = None
    for name in names:
        if name == "A":
            out[name] = LexicalRetriever(fragments)
        elif name in ("B", "C"):
            hybrid = hybrid or HybridRetriever(fragments, embedder)
            if hybrid.vectors is None:
                raise SystemExit(f"Embeddings unavailable: {hybrid.stats['startup_error']}")
            if name == "B":
                out[name] = hybrid
            else:
                c = HybridRetriever(fragments, embedder, rerank=True, rerank_top_n=8, disabled=True)
                c.vectors, c.stats["mode"] = hybrid.vectors, "hybrid"
                out[name] = c
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variants", default="A,B")
    p.add_argument("--cases", default=str(ROOT / "eval/cases_v3.json"))
    p.add_argument("--split", default="dev", help="dev | holdout | all")
    p.add_argument("--kb", default=str(ROOT / "data/knowledge-base.zip"))
    p.add_argument("--local-embeddings", action="store_true")
    p.add_argument("--seed", type=int, default=20261111)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    raw = json.loads(Path(args.cases).read_text(encoding="utf8"))
    cases = raw["cases"] if isinstance(raw, dict) else raw
    if args.split != "all":
        cases = [c for c in cases if c.get("split", "dev") == args.split]
    settings = Settings.from_env()
    fragments = load_fragments(args.kb)
    variants = make_variants(args.variants.split(","), fragments, settings, args.local_embeddings)
    client = LLMClient(settings)

    answers = {}
    for name, retriever in variants.items():
        consultant = Consultant(client, retriever, settings)
        rows = {}
        for case in cases:
            started = time.monotonic()
            result = consultant.respond(ConsultationRequest(f"cmp-{name}-{case['id']}", parse_question(case["question"])),
                                        answer_only=True)
            rows[case["id"]] = {"answer": result.answer, "status": result.status,
                                "error_code": result.debug.get("error_code"), "http_status": result.debug.get("http_status"),
                                "sources": result.debug.get("retrieved_sources", []),
                                "context_chars": result.debug.get("context_chars"),
                                "seconds": round(time.monotonic() - started, 2)}
            print(name, case["id"], rows[case["id"]]["status"], rows[case["id"]]["seconds"], flush=True)
        answers[name] = {"rows": rows, "retriever_stats": getattr(retriever, "stats", None)}

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"model": settings.model, "temperature": settings.temperature, "max_tokens": settings.max_tokens,
            "top_k": settings.top_k, "cases_file": args.cases, "split": args.split, "variants": list(variants)}
    (out / "answers.json").write_text(json.dumps({"meta": meta, "answers": answers}, ensure_ascii=False, indent=1),
                                      encoding="utf8")
    # Blind pairs: control A against each other variant, sides shuffled per case.
    rng = random.Random(args.seed)
    pairs, key = [], {}
    for other in [v for v in variants if v != "A"]:
        for case in cases:
            sides = ["A", other]
            rng.shuffle(sides)
            pid = f"{other}-{case['id']}"
            key[pid] = {"left": sides[0], "right": sides[1]}
            pairs.append({"pair_id": pid, "question": case["question"],
                          "required_facts": [{"fact": f["fact"], "quotes": [s["quote"] for s in f["sources"]]}
                                             for f in case.get("required_facts", [])],
                          "conditional_facts": [{"condition": f["condition"], "fact": f["fact"]}
                                                for f in case.get("conditional_facts", [])],
                          "forbidden_claims": [c["claim"] for c in case.get("forbidden_claims", [])],
                          "acceptable_unknowns": case.get("acceptable_unknowns", []),
                          "left": answers[sides[0]]["rows"][case["id"]]["answer"],
                          "right": answers[sides[1]]["rows"][case["id"]]["answer"],
                          "verdict": None, "major_errors": {"left": [], "right": []},
                          "missing_conditions": {"left": [], "right": []}, "reason": ""})
    (out / "blind_pairs.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=1), encoding="utf8")
    (out / "blind_key.json").write_text(json.dumps(key, indent=1), encoding="utf8")
    print(f"{len(pairs)} pairs -> {out}")


if __name__ == "__main__":
    main()
