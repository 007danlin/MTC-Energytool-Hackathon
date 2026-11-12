from pathlib import Path
import unittest
from contracts import Fragment, Message
from dialogue import retrieval_query
from verified_conditions import VerifiedRetriever, latest_query, single_power


ROOT = Path(__file__).resolve().parents[3]


class VerifiedConditionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = VerifiedRetriever.from_zip(ROOT / 'data/knowledge-base.zip')

    def notes(self, q):
        return '\n'.join(f.text for f in self.r.condition_notes(retrieval_query([Message('user', q)])))

    def test_full_multiline_latest_survives(self):
        q = 'Добрый день!\nСолнечная станция0,48 МВт.\nЭто выше типового диапазона?'
        self.assertEqual(latest_query(retrieval_query([Message('user', q)]))[0], q)
        self.assertIn('15 <= 480 <= 500', self.notes(q))

    def test_power_does_not_read_consumption(self):
        self.assertIsNone(single_power('Потребление420 кВт·ч'))
        self.assertEqual(single_power('Мощность1,4 МВт, потребление420 кВт·ч'), 1400)

    def test_explicit_latest_correction(self):
        self.assertEqual(single_power('Мощность не2,2 МВт, а680 кВт'), 680)
        self.assertIsNone(single_power('Два корпуса430 кВт и460 кВт'))
        self.assertIsNone(single_power('Два корпуса430 и460 кВт'))
        self.assertIsNone(single_power('Два корпуса430 +460 кВт'))

    def test_solar_inclusive_boundaries_and_economic_floor(self):
        self.assertIn('внутри типового', self.notes('Солнечная станция500 кВт — ещё типовой проект?'))
        self.assertIn('индивидуальный', self.notes('Солнечная станция0,51 МВт — типовой проект?'))
        self.assertIn('экономическая граница', self.notes('Солнечная станция14,5 кВт технически запрещена или экономически нецелесообразна?'))

    def test_generation_not_confused_with_grid_capacity(self):
        self.assertEqual(self.notes('У нас присоединённая мощность500 кВт, какую солнечную станцию можно считать типовой?'), '')

    def test_orem_tiers(self):
        self.assertIn('в том числе через посредника', self.notes('Оптовый рынок при мощности680 кВт возможен?'))
        self.assertIn('компанию-посредника', self.notes('Оптовый рынок при мощности0,75 МВт возможен?'))
        self.assertIn('выполнено условие мощности', self.notes('Оптовый рынок при мощности20 МВт возможен?'))

    def test_tariff_not_orem_threshold(self):
        self.assertIn('Категории I и II не подходят', self.notes('Вторая ценовая категория при мощности690 кВт допустима?'))

    def test_roof_remaining_life(self):
        self.assertIn('30 - 12 = 18', self.notes('Солнечные панели на шиферную кровлю12 лет назад уложенную — целесообразно?'))

    def test_archive_duration_never_becomes_product_minimum(self):
        self.assertIn('22 месяцев', self.notes('Для поиска потерь архив22 месяца. Данных достаточно?'))
        self.assertIn('одного года (12 месяцев)', self.notes('Для поиска потерь архив22 месяца. Данных достаточно?'))

    def test_unaffected_query_preserves_full_baseline(self):
        q = retrieval_query([Message('user', 'Сколько стоит солнечная станция50 кВт?')])
        self.assertEqual(self.r.search(q, 4), self.r.lexical.search(q, 4))

    def test_history_uses_user_power_not_assistant_suggestion(self):
        messages = [Message('user', 'У нас700 кВт мощности.'),
                    Message('assistant', 'Может, у вас500 кВт?'),
                    Message('user', 'Можно перейти на вторую категорию?')]
        r = VerifiedRetriever(self.r.lexical, user_messages=messages)
        text = '\n'.join(f.text for f in r.condition_notes(retrieval_query(messages)))
        self.assertIn('мощность 700 кВт', text)
        self.assertIn('Категории I и II не подходят', text)

    def test_no_history_transfer_from_grid_power_to_solar_generation(self):
        messages = [Message('user', 'Присоединённая мощность900 кВт.'),
                    Message('user', 'Солнечная станция попадёт в типовой диапазон?')]
        r = VerifiedRetriever(self.r.lexical, user_messages=messages)
        self.assertEqual(r.condition_notes(retrieval_query(messages)), [])

    def test_no_history_transfer_after_object_switch(self):
        messages = [Message('user', 'У первого завода700 кВт мощности.'),
                    Message('user', 'Теперь другой объект. Можно вторую ценовую категорию?')]
        r = VerifiedRetriever(self.r.lexical, user_messages=messages)
        self.assertEqual(r.condition_notes(retrieval_query(messages)), [])

    def test_no_rule_when_runtime_source_changes(self):
        class Fake:
            fragments = [Fragment('20-products/23-solar.md', 's004', 'Согласование параметров со специалистом.')]
            def search(self, query, top_k): return list(self.fragments)
        r = VerifiedRetriever(Fake())
        self.assertEqual(r.condition_notes('Солнечная станция480 кВт, типовой диапазон?'), [])

    def test_thresholds_are_extracted_from_runtime_source(self):
        class Fake:
            fragments = [Fragment('20-products/23-solar.md', 's004', 'От20 до400 кВт. Типовой диапазон.')]
            def search(self, query, top_k): return list(self.fragments)
        r = VerifiedRetriever(Fake())
        self.assertIn('480 > 400', r.condition_notes('Солнечная станция480 кВт, типовой диапазон?')[0].text)


if __name__ == '__main__':
    unittest.main()
