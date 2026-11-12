import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import hybrid_retrieval as candidate
from dialogue import parse_question, retrieval_query
from retrieval import load_fragments

spec = importlib.util.spec_from_file_location(
    "original_b", PROJECT / "experiments/artem-pr4-20261111/hybrid_retrieval.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


class SyntheticVectors:
    def embed(self, texts, query=False):
        return [candidate._normalize([float(b) - 127 for b in hashlib.sha256(t.encode()).digest()])
                for t in texts]


class FakeTransport:
    def __init__(self, response, clock=None, spend=0):
        self.response, self.clock, self.spend = response, clock, spend
        self.calls = []

    def post(self, url, headers, payload, timeout):
        body = json.loads(payload)
        self.calls.append((url, body, timeout))
        if self.clock is not None:
            self.clock[0] += min(self.spend, timeout)
        data = self.response(body) if callable(self.response) else self.response
        return 200, {}, json.dumps(data).encode()


def good_response(body):
    return {"data": [{"index": i, "embedding": [1.0, 2.0]} for i, _ in enumerate(body["input"])]}


class EmbeddingSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragments = load_fragments(PROJECT / "data/knowledge-base.zip")

    def test_valid_rankings_match_original_for_all_123_questions(self):
        a = original.HybridRetriever(self.fragments, SyntheticVectors())
        b = candidate.HybridRetriever(self.fragments, SyntheticVectors())
        cases = json.loads((PROJECT / "experiments/artem-pr4-20261111/eval/cases_v3.json").read_text())["cases"]
        for case in cases:
            query = retrieval_query(parse_question(case["question"]))
            with self.subTest(case=case["id"]):
                self.assertEqual(a.search(query, 12), b.search(query, 12))
        self.assertEqual(b.stats["fallback_searches"], 0)

    def test_bad_query_vectors_use_exact_a2_fallback_and_trip_breaker(self):
        for bad in ([1.0], [float("nan"), 0.0], [float("inf"), 0.0], [0.0, 0.0], []):
            class Embedder:
                def embed(self, texts, query=False):
                    return [bad if query else [1.0, 0.0] for _ in texts]
            r = candidate.HybridRetriever(self.fragments, Embedder())
            query = "Солнечная станция для склада: окупаемость?"
            expected = r.lexical.search(query, 12)
            for _ in range(3):
                self.assertEqual(r.search(query, 12), expected)
            self.assertEqual(r.stats["fallback_searches"], 3)
            self.assertTrue(r.stats["breaker_open"])

    def test_missing_history_query_vector_falls_back(self):
        class Embedder:
            def embed(self, texts, query=False):
                return [[1.0, 0.0]] if query else [[1.0, 0.0] for _ in texts]
        r = candidate.HybridRetriever(self.fragments, Embedder())
        q = "Сколько?\nКонтекст разговора:\nНужна станция 100кВт"
        self.assertEqual(r.search(q), r.lexical.search(q))
        self.assertEqual(r.stats["fallback_searches"], 1)

    def test_bad_document_vectors_fall_back_before_generation(self):
        for bad in ([0.0, 0.0], [], [float("nan"), 1.0], [float("inf"), 1.0]):
            class Embedder:
                def embed(self, texts, query=False):
                    return [bad for _ in texts]
            r = candidate.HybridRetriever(self.fragments, Embedder())
            self.assertIsNone(r.vectors)
            self.assertEqual(r.stats["mode"], "lexical_fallback")

    def test_api_response_indices_and_vector_validation(self):
        valid = {"index": 0, "embedding": [1, 2]}
        bad_responses = [
            {"data": [valid, valid]},
            {"data": [{"index": -1, "embedding": [1, 2]}, {"index": 1, "embedding": [1, 2]}]},
            {"data": [{"index": 0.5, "embedding": [1, 2]}, {"index": 1, "embedding": [1, 2]}]},
            {"data": [valid]},
            {"data": [{"index": 0, "embedding": [0, 0]}, {"index": 1, "embedding": [1, 2]}]},
            {"data": [{"index": 0, "embedding": [float("nan"), 0]}, {"index": 1, "embedding": [1, 2]}]},
        ]
        for response in bad_responses:
            client = candidate.APIEmbedder("http://test/v1", "dummy", "bge", transport=FakeTransport(response))
            with self.assertRaises((RuntimeError, ValueError, TypeError)):
                client.embed(["one", "two"])

    def test_out_of_order_valid_response_preserves_alignment(self):
        response = {"data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [3, 0]}]}
        client = candidate.APIEmbedder("http://test/v1", "dummy", "bge", transport=FakeTransport(response))
        self.assertEqual(client.embed(["one", "two"]), [[1.0, 0.0], [0.0, 1.0]])

    def test_startup_budget_is_shared_across_batches(self):
        clock = [100.0]
        transport = FakeTransport(good_response, clock, spend=30)
        with patch.object(candidate.time, "monotonic", side_effect=lambda: clock[0]):
            client = candidate.APIEmbedder("http://test/v1", "dummy", "bge", transport=transport,
                                          batch=1, startup_seconds=65)
            with self.assertRaisesRegex(RuntimeError, "embedding_deadline"):
                client.embed(["a", "b", "c", "d", "e"])
        self.assertEqual([x[2] for x in transport.calls], [30.0, 30.0, 5.0])
        self.assertEqual(clock[0], 165.0)

    def test_global_deadline_limits_query_timeout(self):
        transport = FakeTransport(good_response)
        with patch.object(candidate.time, "monotonic", return_value=100):
            client = candidate.APIEmbedder("http://test/v1", "dummy", "bge", transport=transport, deadline=101)
            client.embed(["a"], query=True)
        self.assertEqual(transport.calls[0][2], 1)

    def test_expired_deadline_makes_no_request(self):
        transport = FakeTransport(good_response)
        with patch.object(candidate.time, "monotonic", return_value=100):
            client = candidate.APIEmbedder("http://test/v1", "dummy", "bge", transport=transport, deadline=99)
            with self.assertRaisesRegex(RuntimeError, "embedding_deadline"):
                client.embed(["a"], query=True)
        self.assertEqual(transport.calls, [])

    def test_submission_exists_before_first_embedding_call(self):
        import solution
        from settings import Settings
        cfg = Settings("http://test/v1", "dummy", "mock")
        with tempfile.TemporaryDirectory() as td:
            before = os.getcwd()
            try:
                os.chdir(td)
                def startup(*args, **kwargs):
                    with Path("submission.csv").open(encoding="utf-8") as stream:
                        rows = list(csv.DictReader(stream))
                    self.assertEqual([r["id"] for r in rows], ["one", "two"])
                    self.assertTrue(all(r["answer"] for r in rows))
                    self.assertIsNotNone(kwargs["deadline"])
                    raise ValueError("intentional startup failure")
                with patch.object(solution.Settings, "from_env", return_value=cfg), \
                        patch.object(solution, "find_inputs", return_value=("q.csv", "kb.zip")), \
                        patch.object(solution, "read_questions", return_value=[("one", "one?"), ("two", "two?")]), \
                        patch.object(solution, "create_retriever", side_effect=startup):
                    self.assertEqual(solution.main(), 2)
            finally:
                os.chdir(before)


if __name__ == "__main__":
    unittest.main()
