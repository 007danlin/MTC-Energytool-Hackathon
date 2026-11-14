"""Regression: the dense part of the hybrid retriever must see the whole multi-line message."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogue import parse_question, retrieval_query  # noqa: E402
from hybrid_retrieval import _split_query  # noqa: E402


class SplitQueryTests(unittest.TestCase):
    def test_multiline_message_is_kept_whole(self):
        question = "Здравствуйте!\nНужна солнечная станция 510 кВт.\nЕсть ли ограничения по мощности?"
        latest, history = _split_query(retrieval_query(parse_question(question)))
        self.assertEqual(latest, question)
        self.assertEqual(history, "")

    def test_single_line_and_history(self):
        dialogue = "Пользователь: У нас склад.\nАссистент: Какая мощность?\nПользователь: 120 кВт, что дальше?"
        latest, history = _split_query(retrieval_query(parse_question(dialogue)))
        self.assertEqual(latest, "120 кВт, что дальше?")
        self.assertIn("У нас склад.", history)

    def test_query_without_duplication_is_not_cut(self):
        latest, history = _split_query("Первая строка\nвторая строка\nКонтекст разговора:\nранее")
        self.assertEqual(latest, "Первая строка\nвторая строка")
        self.assertEqual(history, "ранее")


if __name__ == "__main__":
    unittest.main()
