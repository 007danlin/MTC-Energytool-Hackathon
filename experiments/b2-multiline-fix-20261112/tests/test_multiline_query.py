import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import hybrid_retrieval as candidate
from contracts import Message
from dialogue import parse_question, retrieval_query
from retrieval import load_fragments

original = types.ModuleType("frozen_original_b2")
with zipfile.ZipFile(PROJECT / "artifacts/daniel-submission-b2-hybrid.zip") as archive:
    exec(compile(archive.read("hybrid_retrieval.py"), "frozen_original_b2.py", "exec"), original.__dict__)


class CapturingVectors:
    def __init__(self):
        self.queries = []

    def embed(self, texts, query=False):
        if query:
            self.queries.append(list(texts))
        return [candidate._normalize([float(b) - 127 for b in hashlib.sha256(text.encode()).digest()])
                for text in texts]


class MultilineQueryTests(unittest.TestCase):
    def test_plain_single_line_unchanged(self):
        for query in ("Как работает АСКУЭ?", "  Сроки выхода на ОРЭМ?  ", "", "   "):
            with self.subTest(query=query):
                self.assertEqual(candidate._split_query(query), original._split_query(query))

    def test_formatted_single_line_and_history_unchanged(self):
        messages = [Message("user", "Расскажите про солнечные станции."),
                    Message("assistant", "Какова мощность?"), Message("user", "510 кВт")]
        query = retrieval_query(messages)
        self.assertEqual(candidate._split_query(query), original._split_query(query))

    def test_formatted_multiline_retains_latest_once(self):
        latest = "Здравствуйте!\nНужна солнечная станция 510 кВт.\nЕсть ли ограничения по мощности?"
        query = retrieval_query([Message("user", latest)])
        self.assertEqual(candidate._split_query(query), (latest, ""))
        self.assertEqual(original._split_query(query), ("Здравствуйте!", ""))

    def test_blank_lines_and_carriage_returns_are_preserved_inside_latest(self):
        latest = "Здравствуйте!\r\n\r\nМощность — 510 кВт.\n\nЧто уточнить?"
        query = retrieval_query([Message("user", latest)])
        self.assertEqual(candidate._split_query(query), (latest, ""))

    def test_actual_repeated_user_lines_are_not_removed(self):
        latest = "Мощность 510 кВт.\nМощность 510 кВт."
        query = retrieval_query([Message("user", latest)])
        self.assertEqual(candidate._split_query(query), (latest, ""))

    def test_direct_multiline_without_wrapper_is_preserved(self):
        latest = "Здравствуйте!\nНужна АСКУЭ.\nСчётчиков несколько сотен."
        self.assertEqual(candidate._split_query(latest), (latest, ""))

    def test_direct_repeated_lines_without_wrapper_are_preserved(self):
        latest = "АСКУЭ\nАСКУЭ"
        self.assertEqual(candidate._split_query(latest), (latest, ""))

    def test_nonduplicated_multiline_with_history_is_preserved(self):
        latest = "Здравствуйте!\nМожно продолжить расчёт?"
        history = "Нужна солнечная станция.\nЕсть дневное потребление."
        self.assertEqual(candidate._split_query(latest + "\nКонтекст разговора:\n" + history),
                         (latest, history))

    def test_live_search_passes_full_latest_to_query_embedder(self):
        latest = "Здравствуйте!\nНужна солнечная станция 510 кВт.\nЕсть ли ограничения по мощности?"
        messages = [Message("user", "Есть дневной склад."),
                    Message("assistant", "Какая мощность?"), Message("user", latest)]
        query = retrieval_query(messages)
        history = query.partition("\nКонтекст разговора:\n")[2].strip()
        embedder = CapturingVectors()
        retriever = candidate.HybridRetriever(load_fragments(PROJECT / "data/knowledge-base.zip"), embedder)
        self.assertTrue(retriever.search(query, 12))
        self.assertEqual(embedder.queries, [[latest, latest + "\n" + history[-1500:]]])
        self.assertEqual(retriever.stats["fallback_searches"], 0)

    def test_known_single_line_latest_rankings_are_byte_equivalent(self):
        fragments = load_fragments(PROJECT / "data/knowledge-base.zip")
        a = original.HybridRetriever(fragments, CapturingVectors())
        b = candidate.HybridRetriever(fragments, CapturingVectors())
        cases = json.loads((PROJECT / "experiments/artem-pr4-20261111/eval/cases_v3.json").read_text())["cases"]
        checked = 0
        for case in cases:
            messages = parse_question(case["question"])
            if "\n" in messages[-1].content:
                continue
            query = retrieval_query(messages)
            with self.subTest(case=case["id"]):
                self.assertEqual(a.search(query, 12), b.search(query, 12))
            checked += 1
        self.assertGreater(checked, 0)
        self.assertEqual(a.stats["fallback_searches"], 0)
        self.assertEqual(b.stats["fallback_searches"], 0)
        self.assertEqual(a.embedder.queries, b.embedder.queries)


if __name__ == "__main__":
    unittest.main()
