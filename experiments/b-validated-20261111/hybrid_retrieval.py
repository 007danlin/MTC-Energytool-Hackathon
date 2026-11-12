"""Hybrid retriever (BM25 + bge-m3 dense, RRF) with product restrictions.

Same contract as retrieval.LexicalRetriever: search(query, top_k) -> list[Fragment].
Standard library only. Embeddings come from the platform proxy
(POST {LLM_BASE_URL}/embeddings, model EMB_MODEL), computed at start-up from the
knowledge base passed by the platform: no index is shipped, so the document and
query vectors always come from the same service and model.
Optional reranking uses POST {LLM_BASE_URL}/rerank (model RERANKER_MODEL).

Any embedding failure (start-up or per query) degrades to the unchanged A2
lexical result for that call and is recorded in `self.stats`, never raised.
"""
from dataclasses import replace
import json
import math
import re
import threading
import time

from retrieval import LexicalRetriever, load_fragments, topics

RRF_K = 60
DENSE_POOL = 30
RERANK_POOL = 20
# Leaf headings that carry a product's limits and conditions.
GUARD_HEADINGS = ("Чего утверждать нельзя", "Что мы не делаем", "Не подходит", "Важное ограничение",
                  "Что нужно от клиента")
# Reference sections that hold the product's scope and numeric caveats.
PRODUCT_SCOPE = {
    "20-products/21-orem.md": ("Выход на оптовый рынок",),
    "20-products/22-askue.md": ("Облачная платформа учёта", "Платформа учёта"),
    "20-products/23-solar.md": ("Солнечные электростанции", "Солнечные станции"),
    "20-products/24-losses.md": ("Поиск коммерческих потерь",),
    "20-products/25-meter-reading.md": ("Распознавание показаний",),
}
NUMERIC = re.compile(r"скольк|мощн|квт|мвт|процент|цен[аыуе]|стоим|окуп|тариф|порог|срок|гарант|\bлет\b|\bгод|руб|\d")
# Without a leading product, the general boundaries tell the model what it may not invent.
GENERAL_RULES = (("00-reference/02-product-scope-and-limits.md", ("Общие границы", "Когда требуется специалист")),
                 ("20-products/20-portfolio.md", ("Чего утверждать нельзя",)))
CALC = re.compile(r"оценк|расчет|невыгод|стоим|эконом|бесплат")


def _split_query(query):
    current, _, history = query.partition("\nКонтекст разговора:\n")
    lines = [line for line in current.split("\n") if line.strip()]
    latest = lines[0] if lines else current
    return latest.strip(), history.strip()


def _vector_norm(vector, dimension=None):
    """Reject invalid embeddings before they can silently corrupt ranking."""
    if not vector or (dimension is not None and len(vector) != dimension):
        raise RuntimeError("embedding_shape")
    if any(isinstance(x, bool) or not math.isfinite(x) for x in vector):
        raise RuntimeError("embedding_nonfinite")
    squared = sum(x * x for x in vector)
    if not math.isfinite(squared) or squared <= 0:
        raise RuntimeError("embedding_invalid_norm")
    return math.sqrt(squared)


def _normalize(vector):
    norm = _vector_norm(vector)
    return [x / norm for x in vector]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class APIEmbedder:
    """OpenAI-compatible /embeddings and /rerank through the shared HTTP transport."""

    def __init__(self, base_url, api_key, model, *, rerank_model=None, rerank_key=None,
                 timeout=30.0, attempts=2, transport=None, batch=16, deadline=None,
                 startup_seconds=90.0):
        from llm_client import HTTPTransport
        self.base = base_url.rstrip("/")
        for suffix in ("/chat/completions", "/embeddings"):
            if self.base.endswith(suffix):
                self.base = self.base[: -len(suffix)]
        self.key, self.model = api_key, model
        self.rerank_model, self.rerank_key = rerank_model, rerank_key or api_key
        self.timeout, self.attempts, self.batch = timeout, attempts, batch
        self.transport = transport or HTTPTransport()
        self.deadline = deadline
        self.startup_deadline = time.monotonic() + startup_seconds
        if deadline is not None:
            self.startup_deadline = min(self.startup_deadline, deadline)

    def _post(self, path, key, payload, timeout=None, attempts=None, deadline=None):
        timeout = timeout or self.timeout
        attempts = attempts or self.attempts
        if self.deadline is not None:
            deadline = min(deadline, self.deadline) if deadline is not None else self.deadline
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
                   "Accept": "application/json"}
        last = None
        for attempt in range(attempts):
            remaining = timeout if deadline is None else deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("embedding_deadline")
            try:
                status, _, raw = self.transport.post(self.base + path, headers, body, min(timeout, remaining))
                if status == 200:
                    return json.loads(raw)
                last = RuntimeError(f"http_{status}")
                if status not in (408, 429) and status < 500:
                    break
            except Exception as exc:  # transport errors carry no secrets
                last = RuntimeError(type(exc).__name__)
            if attempt + 1 < attempts:
                pause = 0.5 * (attempt + 1)
                if deadline is not None and time.monotonic() + pause >= deadline:
                    raise RuntimeError("embedding_deadline")
                time.sleep(pause)
        raise last or RuntimeError("unavailable")

    def embed(self, texts, *, query=False):
        # Queries are on the answer path: short timeout, single attempt.
        timeout, attempts = (8.0, 1) if query else (None, None)
        vectors = []
        for start in range(0, len(texts), self.batch):
            chunk = texts[start:start + self.batch]
            data = self._post("/embeddings", self.key, {"model": self.model, "input": chunk},
                              timeout, attempts,
                              deadline=self.deadline if query else self.startup_deadline)["data"]
            if not isinstance(data, list) or len(data) != len(chunk):
                raise RuntimeError("embedding_count_mismatch")
            out = [None] * len(chunk)
            for i, item in enumerate(data):
                index = item.get("index", i)
                if type(index) is not int or not 0 <= index < len(chunk) or out[index] is not None:
                    raise RuntimeError("embedding_index_mismatch")
                out[index] = _normalize([float(x) for x in item["embedding"]])
            if any(v is None for v in out):
                raise RuntimeError("embedding_count_mismatch")
            vectors.extend(out)
        return vectors

    def rerank(self, query, documents, top_n):
        data = self._post("/rerank", self.rerank_key, {"model": self.rerank_model, "query": query,
                                                       "documents": documents, "top_n": top_n}, 8.0, 1)
        entries = data.get("results", data.get("data", []))
        return [int(e["index"]) for e in entries if 0 <= int(e["index"]) < len(documents)]


class HybridRetriever:
    """Variant B (rerank=False) or C (rerank=True). Falls back to A2 on embedding errors."""

    BREAKER = 3  # consecutive query-embedding failures before dense search is switched off

    def __init__(self, fragments, embedder, *, rerank=False, rerank_top_n=8, disabled=False, general_rules=False,
                 rerank_pool=RERANK_POOL):
        self.fragments = tuple(fragments)
        self.lexical = LexicalRetriever(self.fragments)
        self.embedder, self.rerank, self.rerank_top_n = embedder, rerank, rerank_top_n
        self.general_rules = general_rules
        self.rerank_pool = rerank_pool
        self.by_id = {f.source_id: f for f in self.fragments}
        self.stats = {"mode": "hybrid", "fallback_searches": 0, "rerank_errors": 0, "startup_error": None,
                      "breaker_open": False}
        self._lock = threading.Lock()
        self._failures = 0
        if disabled:
            self.vectors = None
            self.stats["mode"] = "a2_forced"
            return
        try:
            self.vectors = embedder.embed([f.text for f in self.fragments])
            if (not self.vectors or len(self.vectors) != len(self.fragments)
                    or len({len(v) for v in self.vectors}) != 1):
                raise RuntimeError("embedding_shape")
            for vector in self.vectors:
                _vector_norm(vector)
        except Exception as exc:
            self.vectors = None
            self.stats.update(mode="lexical_fallback", startup_error=str(exc)[:80])

    @classmethod
    def from_zip(cls, path, embedder, **kwargs):
        return cls(load_fragments(path), embedder, **kwargs)

    def _note(self, key):
        with self._lock:
            self.stats[key] += 1

    def _dense_ranking(self, latest, history):
        texts = [latest] + ([latest + "\n" + history[-1500:]] if history else [])
        vectors = self.embedder.embed(texts, query=True)
        if len(vectors) != len(texts):
            raise RuntimeError("embedding_count_mismatch")
        dimension = len(self.vectors[0])
        for vector in vectors:
            _vector_norm(vector, dimension)
        scored = []
        for i, doc in enumerate(self.vectors):
            score = _dot(vectors[0], doc)
            if len(vectors) > 1:
                score = 0.65 * score + 0.35 * _dot(vectors[1], doc)
            scored.append((score, i))
        scored.sort(key=lambda item: (-item[0], self.fragments[item[1]].source_id))
        return [(self.fragments[i].source_id, s) for s, i in scored[:DENSE_POOL]]

    def _guards(self, ranked, query):
        """Restrictions of the products that actually lead the ranking, never of incidental ones."""
        products = []
        for source_id in ranked[:4]:
            doc = source_id.split("#")[0]
            if doc in PRODUCT_SCOPE and doc not in products:
                products.append(doc)
        products = products[:2]
        q = query.lower().replace("ё", "е")
        extra = []
        for doc in products:
            for fragment in self.fragments:
                heading = fragment.text.split("\n", 1)[0]
                leaf = heading.split(" > ")[-1]
                if fragment.document_id == doc and any(leaf.startswith(h) for h in GUARD_HEADINGS):
                    extra.append(fragment)
                elif fragment.document_id == "00-reference/02-product-scope-and-limits.md" and \
                        any(leaf.startswith(name) for name in PRODUCT_SCOPE[doc]):
                    extra.append(fragment)
                elif (fragment.document_id == "00-reference/01-numbers-and-indicators.md" and NUMERIC.search(q)
                      and any(leaf.startswith(name) for name in PRODUCT_SCOPE[doc])):
                    extra.append(fragment)
        if not products and self.general_rules:
            extra.extend(f for f in self.fragments for doc, leaves in GENERAL_RULES
                         if f.document_id == doc and f.text.split("\n", 1)[0].split(" > ")[-1] in leaves)
        if CALC.search(q):
            extra.extend(f for f in self.fragments if f.document_id == "00-reference/03-calculation-and-requests.md"
                         and "Бесплатная предварительная оценка" in f.text.split("\n", 1)[0])
        return extra

    def ranked_ids(self, query, top_k=12):
        """Primary ranking only (no restrictions); used for @k diagnostics."""
        latest, history = _split_query(query)
        lexical = [f.source_id for f in self.lexical.search(query, top_k) if f.score > 0][:top_k]
        dense = [sid for sid, _ in self._dense_ranking(latest, history)]
        scores = {}
        for ranking in (lexical, dense):
            for pos, sid in enumerate(ranking):
                scores[sid] = scores.get(sid, 0.0) + 1.0 / (RRF_K + pos + 1)
        fused = sorted(scores, key=lambda sid: (-scores[sid], sid))
        if self.rerank:
            pool = fused[:self.rerank_pool]
            try:
                order = self.embedder.rerank(latest if not history else latest + "\n" + history[-600:],
                                             [self.by_id[s].text for s in pool], len(pool))
                head = [pool[i] for i in order]
                fused = head + [s for s in pool if s not in head] + fused[self.rerank_pool:]
            except Exception:
                self._note("rerank_errors")
        return fused, scores

    def search(self, query, top_k=12):
        if top_k <= 0:
            return []
        if self.vectors is None:
            self._note("fallback_searches")
            return self.lexical.search(query, top_k)
        try:
            fused, scores = self.ranked_ids(query, top_k)
            with self._lock:
                self._failures = 0
        except Exception:
            with self._lock:
                self.stats["fallback_searches"] += 1
                self._failures += 1
                if self._failures >= self.BREAKER and self.vectors is not None:
                    self.vectors = None
                    self.stats.update(mode="lexical_fallback", breaker_open=True)
            return self.lexical.search(query, top_k)
        primary = fused[: (self.rerank_top_n if self.rerank else top_k)]
        result, seen = [], set()
        for sid in primary:
            result.append(replace(self.by_id[sid], score=round(scores.get(sid, 0.0), 5)))
            seen.add(sid)
        for fragment in self._guards(primary, query):
            if fragment.source_id not in seen:
                result.append(fragment)
                seen.add(fragment.source_id)
        return result


def create_retriever(knowledge_zip, settings, environ=None, *, rerank=None, deadline=None):
    """Factory for solution.py: hybrid when the embedding service answers, else A2 (observable)."""
    import os
    from settings import env_first
    env = os.environ if environ is None else environ
    get = lambda *names, default="": env_first(*names, default=default, environ=env)
    model = get("EMB_MODEL", default="baai/bge-m3")
    rerank_model = get("RERANKER_MODEL")
    use_rerank = bool(rerank_model) and get("HYBRID_RERANK", default="0") == "1" if rerank is None else rerank
    disabled = get("RETRIEVAL_MODE", default="hybrid").lower() == "a2"
    try:
        top_n = max(1, min(20, int(get("RERANKER_TOP_N", default="8"))))
    except ValueError:
        top_n = 8
    embedder = APIEmbedder(settings.base_url, get("EMBEDDER_API_KEY", default=settings.api_key), model,
                           rerank_model=rerank_model or None,
                           rerank_key=get("RERANKER_API_KEY", default=settings.api_key), deadline=deadline)
    return HybridRetriever.from_zip(knowledge_zip, embedder, rerank=use_rerank, rerank_top_n=top_n,
                                    disabled=disabled)
