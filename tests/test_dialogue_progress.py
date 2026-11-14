"""Structured consultation must progress after a short answer, without hiding errors."""
import copy
import json
import unittest

from consultant import Consultant, repeats_previous_answer
from contracts import ConsultationRequest, Fragment, Message
from llm_client import ModelError
from retrieval import FixedRetriever
from settings import Settings

CFG = Settings('http://localhost/v1', 'test', 'fixture', attempts=1)
SOURCE = Fragment('test.md', 's1', 'Учёт показаний помогает сравнивать потребление за одинаковые периоды.')
FIRST = 'Для подбора подходящего решения нужно уточнить данные вашего объекта. У вас есть приборы учёта и как сейчас собираются показания?'
NEXT = 'Приборы учёта уже есть. Как сейчас собираете показания: вручную или автоматически?'


def payload(answer, **overrides):
    return dict({'answer': answer, 'status': 'clarification', 'citations': [],
                 'contacts': [], 'intent': {}, 'summary': {}}, **overrides)


class Client:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.deadlines = []

    def complete(self, messages, deadline=None):
        self.calls.append(copy.deepcopy(messages))
        self.deadlines.append(deadline)
        value = self.responses[min(len(self.calls)-1, len(self.responses)-1)]
        if isinstance(value, Exception):
            raise value
        return json.dumps(value, ensure_ascii=False)


class DialogueProgressTests(unittest.TestCase):
    def request(self, latest='Есть приборы учёта'):
        return ConsultationRequest('progress-test', [Message('user', 'Хочу уменьшить потребление в частном доме.'),
                                                    Message('assistant', FIRST), Message('user', latest)])

    def run_consultation(self, client, request=None, **kwargs):
        return Consultant(client, FixedRetriever([SOURCE]), CFG).respond(request or self.request(), **kwargs)

    def test_short_reply_has_explicit_focus_without_changing_evidence_indices(self):
        client = Client(payload(NEXT, summary={'parameters': [
            {'value':'wrong paraphrase', 'quote':'Есть приборы учёта', 'message_index':2}]}))
        result = self.run_consultation(client)
        context = json.loads(client.calls[0][1]['content'])
        self.assertEqual(context['latest_user_message'], {'index':2,'content':'Есть приборы учёта'})
        self.assertEqual([m['index'] for m in context['messages']], [0,1,2])
        self.assertEqual(result.summary['parameters'], [{'value':'Есть приборы учёта','message_index':2}])
        self.assertEqual(result.answer, NEXT)
        self.assertEqual(result.debug['repairs'], 0)

    def test_repeated_answer_is_repaired_within_existing_budget(self):
        client = Client(payload(FIRST), payload(NEXT))
        result = self.run_consultation(client, deadline=12345)
        self.assertEqual(result.answer, NEXT)
        self.assertEqual(result.debug['repairs'], 1)
        self.assertEqual(client.deadlines, [12345,12345])
        self.assertIn('оставшееся', client.calls[1][-1]['content'])
        self.assertIn('latest_user_message', client.calls[1][-1]['content'])
        self.assertEqual(len(client.calls), 2)

    def test_repeated_short_question_and_punctuation_changes_are_detected(self):
        request = self.request()
        request.messages[1] = Message('assistant', 'У вас есть приборы учёта?')
        self.assertTrue(repeats_previous_answer('У вас есть приборы учета?!', request.messages))

    def test_no_infinite_retry_or_fabricated_fallback_when_repair_stalls(self):
        client = Client(payload(FIRST), payload(FIRST))
        result = self.run_consultation(client)
        self.assertEqual(result.status, 'technical_error')
        self.assertEqual(result.debug['error_code'], 'repeated_answer')
        self.assertEqual(result.debug['repairs'], 1)
        self.assertNotEqual(result.answer, FIRST)
        self.assertEqual(len(client.calls), 2)

    def test_requested_repeat_and_identical_resubmission_are_allowed(self):
        for latest in ['Повтори, пожалуйста, предыдущий ответ', 'Напомните свой ответ',
                       'Хочу уменьшить потребление в частном доме.']:
            with self.subTest(latest=latest):
                client = Client(payload(FIRST))
                result = self.run_consultation(client, self.request(latest))
                self.assertEqual(result.answer, FIRST)
                self.assertEqual(len(client.calls), 1)

    def test_short_acknowledgement_and_new_followup_are_not_false_positives(self):
        request = self.request('Спасибо')
        request.messages[1] = Message('assistant', 'Пожалуйста!')
        self.assertFalse(repeats_previous_answer('Пожалуйста!', request.messages))
        self.assertFalse(repeats_previous_answer(FIRST + ' Уточните период сравнения.', self.request().messages))

    def test_progress_repair_does_not_bypass_citation_validation(self):
        bad = payload(NEXT, status='answered', citations=[{'source_id':SOURCE.source_id,'quote':'Выдуманная цитата.'}])
        client = Client(payload(FIRST), bad)
        result = self.run_consultation(client)
        self.assertEqual(result.status, 'technical_error')
        self.assertEqual(result.debug['error_code'], 'ungrounded_citation')
        self.assertEqual(len(client.calls), 2)

    def test_progress_repair_does_not_hide_transport_deadline(self):
        client = Client(payload(FIRST), ModelError('deadline_exceeded'))
        result = self.run_consultation(client)
        self.assertEqual(result.status, 'technical_error')
        self.assertEqual(result.debug['error_code'], 'deadline_exceeded')
        self.assertEqual(len(client.calls), 2)

    def test_progression_and_schema_repair_share_single_repair(self):
        client = Client({'answer':FIRST}, payload(FIRST), payload(NEXT))
        result = self.run_consultation(client)
        self.assertEqual(result.status, 'technical_error')
        self.assertEqual(result.debug['error_code'], 'repeated_answer')
        self.assertEqual(len(client.calls), 2)

    def test_answer_only_path_is_unchanged(self):
        client = Client(payload(FIRST))
        result = self.run_consultation(client, answer_only=True)
        self.assertEqual(result.answer, FIRST)
        self.assertNotIn('latest_user_message', json.loads(client.calls[0][1]['content']))
        self.assertEqual(len(client.calls), 1)


if __name__ == '__main__':
    unittest.main()
