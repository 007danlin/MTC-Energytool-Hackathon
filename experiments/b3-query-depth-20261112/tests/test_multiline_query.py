import json
import unittest

from contracts import Fragment
from dialogue import parse_question, retrieval_query
from hybrid_retrieval import HybridRetriever, _split_query, create_retriever
from retrieval import LexicalRetriever
from settings import Settings


class RecordingEmbedder:
    def __init__(self):
        self.queries = []
    def embed(self, texts, query=False):
        if query:
            self.queries.append(list(texts))
        return [[1.0, 0.0] for _ in texts]


class MultilineQueryTests(unittest.TestCase):
    def test_all_current_lines_reach_embeddings_once(self):
        message = 'Здравствуйте!\n\nНужна солнечная станция 510 кВт.\nЕсть ли ограничения по мощности?'
        forms = [message, 'Пользователь: ' + message,
                 json.dumps([{'role': 'user', 'content': message}], ensure_ascii=False)]
        for raw in forms:
            with self.subTest(raw=raw):
                e = RecordingEmbedder()
                r = HybridRetriever([Fragment('solar.md','s001','Солнечная станция')], e)
                r.search(retrieval_query(parse_question(raw)), 4)
                self.assertEqual(e.queries, [[message]])

    def test_latest_multiline_and_history_stay_separate(self):
        raw = json.dumps([
            {'role': 'user', 'content': 'Мы СНТ, 120 участков.'},
            {'role': 'assistant', 'content': 'Какая задача?'},
            {'role': 'user', 'content': 'Нужен учёт.\nИ удалённое управление нагрузкой.'}], ensure_ascii=False)
        e = RecordingEmbedder()
        r = HybridRetriever([Fragment('metering.md','s001','Учёт и управление')], e)
        r.search(retrieval_query(parse_question(raw)), 4)
        self.assertEqual(e.queries[0][0], 'Нужен учёт.\nИ удалённое управление нагрузкой.')
        self.assertEqual(e.queries[0][1], 'Нужен учёт.\nИ удалённое управление нагрузкой.\nМы СНТ, 120 участков.\nКакая задача?')

    def test_raw_multiline_query_is_not_truncated_or_deduplicated(self):
        self.assertEqual(_split_query('Строка\nСтрока'), ('Строка\nСтрока', ''))
        self.assertEqual(_split_query('Привет\nВопрос\nКонтекст разговора:\nИстория'),
                         ('Привет\nВопрос', 'История'))

    def test_windows_newlines_and_repeated_lines_inside_message_survive(self):
        message = 'Здравствуйте!\r\nВопрос\r\nВопрос'
        self.assertEqual(_split_query(retrieval_query(parse_question(message))), (message, ''))

    def test_fallback_preserves_requested_depth(self):
        fragments = [Fragment('x.md', 's%03d' % i, 'Солнечная станция мощность ' + str(i)) for i in range(20)]
        class BrokenEmbedder:
            def embed(self, texts, query=False):
                if query:
                    raise RuntimeError('unavailable')
                return [[1.0, 0.0] for _ in texts]
        base = {'LLM_BASE_URL':'http://local/v1','LLM_API_KEY':'local','LLM_MODEL':'model'}
        query = retrieval_query(parse_question('Здравствуйте!\nСолнечная станция мощность 10'))
        for depth in (1, 4, 8, 12):
            with self.subTest(depth=depth):
                cfg = Settings.from_env(dict(base, TOP_K=str(depth)))
                expected = LexicalRetriever(fragments).search(query, depth)
                for disabled in (False, True):
                    r = HybridRetriever(fragments, BrokenEmbedder(), disabled=disabled)
                    self.assertEqual(r.search(query, cfg.top_k), expected)

