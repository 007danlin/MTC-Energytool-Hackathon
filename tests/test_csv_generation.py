"""Regression cases for losing useful text to backend-only schema validation."""
import json
from pathlib import Path
import tempfile
import unittest

from consultant import Consultant, TECHNICAL_ANSWER
from contracts import ConsultationRequest, Message
from dialogue import retrieval_query
from llm_client import LLMClient, ModelError
from retrieval import FixedRetriever
from solution import run
from test_core import CFG, FRAGMENT, ScriptedClient, Transport, payload, success


class CSVGenerationTests(unittest.TestCase):
    def setUp(self):
        self.request = ConsultationRequest("csv-test", [Message("user", "Объясните тестовое решение.")])

    def service(self, client):
        return Consultant(client, FixedRetriever([FRAGMENT]), CFG)

    def test_plain_answer_survives_without_backend_schema(self):
        answer = "Сведения доступны в предоставленной базе. Какие параметры объекта известны?"
        client = ScriptedClient(answer)
        result = self.service(client).respond(self.request, answer_only=True)
        self.assertEqual(result.answer, answer)
        self.assertEqual(len(client.calls), 1)
        context = json.loads(client.calls[0][1]["content"])
        self.assertNotIn("lead_so_far", context)
        self.assertIn(FRAGMENT.text, str(context))
        self.assertEqual(result.sources, [])
        self.assertEqual(result.debug["evidence_validation"], "not_performed")
        self.assertFalse(result.summary["sent"])

    def test_optional_json_wrapper_does_not_require_contact_schema(self):
        client = ScriptedClient('```json\n{"answer": "Полезный ответ.", "citations": [{"quote": "неточная цитата"}]}\n```')
        result = self.service(client).respond(self.request, answer_only=True)
        self.assertEqual(result.answer, "Полезный ответ.")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result.sources, [])

    def test_backend_still_rejects_ungrounded_citations(self):
        client = ScriptedClient(payload(citations=[{"source_id": FRAGMENT.source_id, "quote": "Выдуманная цитата длиннее 12 символов"}]))
        result = self.service(client).respond(self.request)
        self.assertEqual(result.status, "technical_error")
        self.assertEqual(result.debug["error_code"], "ungrounded_citation")
        self.assertEqual(len(client.calls), 2)

    def test_csv_runner_really_uses_plain_path(self):
        client = ScriptedClient("Обычный ответ без JSON.")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "submission.csv"
            statuses = run([("007", "Первый вопрос"), ("008", "Второй вопрос")], self.service(client), CFG, output)
            self.assertEqual(statuses, ["answered", "answered"])
            self.assertNotIn(TECHNICAL_ANSWER, output.read_text())
        self.assertEqual(len(client.calls), 2)

    def test_generation_failure_remains_visible(self):
        client = ScriptedClient(ModelError("api_error", status=401))
        result = self.service(client).respond(self.request, answer_only=True)
        self.assertEqual(result.status, "technical_error")
        self.assertEqual(result.debug["http_status"], 401)
        self.assertEqual(result.answer, TECHNICAL_ANSWER)

    def test_plain_answer_never_claims_lead_sent(self):
        client = ScriptedClient("Ваша заявка отправлена менеджеру. Продолжим консультацию.")
        result = self.service(client).respond(self.request, answer_only=True)
        self.assertNotIn("отправлена менеджеру", result.answer)
        self.assertIn("Продолжим консультацию", result.answer)

    def test_long_reply_retains_subject_of_assistant_question(self):
        query = retrieval_query([Message("user", "Хочу сократить расходы."),
                                 Message("assistant", "Общие слова. Какая у вас ценовая категория?"),
                                 Message("user", "Четвёртая, мощность 500 кВт, расход 100000 кВт·ч за месяц.")])
        self.assertIn("ценовая категория", query)
        self.assertNotIn("Общие слова", query)

    def test_reasoning_with_only_closing_tag_is_not_exposed(self):
        client = LLMClient(CFG, Transport(success("private reasoning</think>Готовый ответ.")))
        self.assertEqual(client.complete([]), "Готовый ответ.")

    def test_unclosed_reasoning_is_not_used_as_an_answer(self):
        transport = Transport(success("<think>private"), success("<think>private"))
        with self.assertRaises(ModelError):
            LLMClient(CFG, transport, lambda _: None).complete([])

    def test_length_cutoff_is_not_silently_treated_as_complete(self):
        transport = Transport(success("Экономия гарантирована, если", "length"))
        with self.assertRaises(ModelError) as caught:
            LLMClient(CFG, transport, lambda _: None).complete([])
        self.assertEqual(caught.exception.code, "truncated_response")
        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
