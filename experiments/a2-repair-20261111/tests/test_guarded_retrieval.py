import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from consultant import Consultant
from contracts import ConsultationRequest, Fragment, Message
from guarded_retrieval import GuardedRetriever, _is_guard
from llm_client import LLMClient
from retrieval import LexicalRetriever
from settings import Settings


def frag(doc, section, text, score=0.0):
    return Fragment(doc, section, text, score)


class CaptureTransport:
    def __init__(self):
        self.payloads = []

    def post(self, url, headers, payload, timeout):
        self.payloads.append(json.loads(payload))
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'Тестовый ответ.'},
                                               'finish_reason': 'stop'}]}).encode()


class GuardedRetrieverTests(unittest.TestCase):
    def test_roles_include_scope_and_intro_but_not_inputs(self):
        for heading in ['Кому подходит > Не подходит промышленным потребителям',
                        'Кому подходит > Не подходит энергосбытовым компаниям',
                        'Что мы не делаем', 'Чего утверждать нельзя', 'Целевой клиент',
                        'Кому не подходит', 'Важное ограничение']:
            with self.subTest(heading=heading):
                self.assertTrue(_is_guard(frag('20-products/a.md', '1',
                                              'Продукт > '+heading+'\nПолное ограничение.')))
        self.assertTrue(_is_guard(frag('20-products/a.md', '1',
                                      'Продукт\n**Кому:** сетевым организациям.')))
        for heading in ['Что нужно от клиента', 'Что нужно от клиента > Ограничения',
                        'Какие сведения могут понадобиться', 'Как начать работу', 'Стоимость']:
            with self.subTest(heading=heading):
                self.assertFalse(_is_guard(frag('20-products/a.md', '1',
                                               'Продукт > '+heading+'\nОписание.')))

    def test_original_candidates_order_scores_and_identity_are_preserved(self):
        a = frag('20-products/a.md', '1', 'А > Возможность\nДанные', 2.5)
        old_guard = frag('20-products/a.md', '2', 'А > Чего утверждать нельзя\nНет гарантии')
        support = frag('00-reference/scope.md', '1', 'Справка > Ограничения\nСправка')
        missing = frag('20-products/a.md', '3', 'А > Что мы не делаем\nНе продаём энергию')
        original = [a, old_guard, support]
        retriever = GuardedRetriever(original+[missing])
        with patch.object(LexicalRetriever, 'search', return_value=original):
            result = retriever.search('запрос', 1)
        self.assertEqual(result, original+[missing])
        for before, after in zip(original, result):
            self.assertIs(before, after)
        self.assertEqual(original, [a, old_guard, support])

    def test_only_first_two_primary_product_documents_are_expanded(self):
        original = [frag('20-products/20-portfolio.md', '1', 'Портфель\nОбзор', 9),
                    frag('20-products/26-general.md', '1', 'Общее\nДанные', 8),
                    frag('00-reference/limits.md', '1', 'Справка\nДанные', 7)]
        original += [frag('20-products/'+x+'.md', '1', x+' > Возможность\nДанные', 6-i)
                     for i, x in enumerate('abc')]
        original += [frag('20-products/d.md', '1', 'D > Что нужно от клиента\nДанные')]
        guards = [frag('20-products/'+x+'.md', '2', x+' > Не подходит\nОграничение')
                  for x in ['a', 'b', 'c', 'd', '20-portfolio', '26-general']]
        retriever = GuardedRetriever(original+guards)
        with patch.object(LexicalRetriever, 'search', return_value=original):
            result = retriever.search('запрос', 10)
        self.assertEqual(result, original+guards[:2])

    def test_no_matches_and_nonpositive_top_k_do_not_add_guards(self):
        retriever = GuardedRetriever([frag('20-products/a.md', '1',
                                          'Платформа > Кому подходит\nСетям')])
        self.assertEqual(retriever.search('zzzzzzzz', 12), [])
        self.assertEqual(retriever.search('платформа', 0), [])
        self.assertEqual(retriever.search('платформа', -1), [])

    def test_inherited_from_zip_constructs_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)/'kb.zip'
            with ZipFile(archive, 'w') as z:
                z.writestr('20-products/a.md', '# Платформа\nОписание.\n## Что мы не делаем\nНе продаём энергию.')
            retriever = GuardedRetriever.from_zip(archive)
            self.assertIsInstance(retriever, GuardedRetriever)
            self.assertEqual(len(retriever.fragments), 2)
            self.assertIn('20-products/a.md', retriever._guards_by_document)

    def api_sources(self, retriever, budget, query="Как работает платформа?", top_k=2):
        transport = CaptureTransport()
        cfg = Settings('http://test.invalid/v1', 'test-only', 'test-model',
                       context_chars=budget, top_k=top_k, attempts=1)
        service = Consultant(LLMClient(cfg, transport), retriever, cfg)
        result = service.respond(ConsultationRequest('guard-test',
                                 [Message('user', query)]), answer_only=True)
        self.assertEqual(result.status, 'answered')
        self.assertEqual(len(transport.payloads), 1)
        return json.loads(transport.payloads[0]['messages'][1]['content'])['sources']

    def test_actual_api_payload_preserves_a2_prefix_under_tight_budgets(self):
        first = frag('20-products/a.md', '1', 'A > Возможность\nКраткий факт.', 5)
        oversized = frag('20-products/a.md', '2', 'A > Детали\n'+'д'*600, 4)
        old_guard = frag('20-products/a.md', '3', 'A > Чего утверждать нельзя\nНе обещать гарантию.')
        support = frag('00-reference/scope.md', '1', 'Справка\nКраткое условие.')
        large_guard = frag('20-products/a.md', '4', 'A > Кому не подходит\n'+'г'*500)
        small_guard = frag('20-products/a.md', '5', 'A > Что мы не делаем\nНе продаём энергию.')
        original = [first, oversized, old_guard, support]
        fragments = original+[large_guard, small_guard]
        base, guarded = LexicalRetriever(fragments), GuardedRetriever(fragments)
        accepted_cost = sum(len(f.text) for f in [first, old_guard, support])
        budgets = [len(first.text), accepted_cost, accepted_cost+len(small_guard.text)-1,
                   accepted_cost+len(small_guard.text), 5000]
        for budget in budgets:
            with self.subTest(budget=budget), patch.object(LexicalRetriever, 'search', return_value=original):
                before = self.api_sources(base, budget)
                after = self.api_sources(guarded, budget)
            self.assertEqual(after[:len(before)], before)
            self.assertLessEqual(sum(len(s['text']) for s in after), budget)
            known = {f.source_id: f.text for f in fragments}
            for source in after:
                self.assertEqual(source['text'], known[source['source_id']])
            if budget == accepted_cost+len(small_guard.text):
                self.assertEqual(after[len(before):],
                                 [{'source_id':small_guard.source_id, 'text':small_guard.text}])
                self.assertNotIn(large_guard.source_id, [s['source_id'] for s in after])

    def test_real_kb_missing_industrial_loss_scope_guard(self):
        archive = Path(os.environ['ENERGYTOOL_TEST_KB']) if 'ENERGYTOOL_TEST_KB' in os.environ else Path(__file__).resolve().parents[3]/'data/knowledge-base.zip'
        if not archive.is_file():
            self.skipTest('Optional real KB fixture is not mounted in isolated unit-test runtime')
        base, guarded = LexicalRetriever.from_zip(archive), GuardedRetriever.from_zip(archive)
        query = 'Поиск коммерческих потерь электроэнергии'
        original, result = base.search(query, 12), guarded.search(query, 12)
        self.assertEqual(result[:len(original)], original)
        missing_id = '20-products/24-losses.md#s005'
        self.assertNotIn(missing_id, [f.source_id for f in original])
        self.assertIn(missing_id, [f.source_id for f in result])
        expected = next(f for f in base.fragments if f.source_id == missing_id)
        self.assertEqual(next(f.text for f in result if f.source_id == missing_id), expected.text)
        for budget in [4000, 32000]:
            before = self.api_sources(base, budget, query, top_k=12)
            after = self.api_sources(guarded, budget, query, top_k=12)
            self.assertEqual(after[:len(before)], before)
            if budget == 32000:
                self.assertIn({'source_id':missing_id, 'text':expected.text}, after)


if __name__ == '__main__':
    unittest.main()
