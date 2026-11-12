"""Behavioral retrieval regressions using small synthetic documents, no demo answers."""
import unittest

from contracts import Fragment
from retrieval import LexicalRetriever, tokens


def fragment(doc, chunk, title, body):
    return Fragment(doc, chunk, title + "\n" + body)


class RetrievalQualityTests(unittest.TestCase):
    def test_specific_body_beats_repeated_product_title(self):
        target = fragment("solar.md", "one", "Солнечные станции > Размещение",
                          "Вертикальный фасад здания требует обследования конструкций.")
        distractors = [fragment("solar.md", str(i), "Солнечные станции > Общая информация",
                                "Солнечные станции помогают предприятиям.") for i in range(12)]
        result = LexicalRetriever([target] + distractors).search("Солнечные панели на фасаде?", 3)
        self.assertEqual(result[0].source_id, target.source_id)

    def test_faq_heading_is_searchable_without_repeating_question_in_body(self):
        target = fragment("solar.md", "finance", "Солнечные станции > Нет средств на капитальные затраты",
                          "Доступна рассрочка; условия определяются проектом.")
        others = [fragment("solar.md", "intro" + str(i), "Солнечные станции",
                           "Солнечная станция на крыше.") for i in range(10)]
        result = LexicalRetriever([target] + others).search("Солнечная станция без капитальных затрат?")
        self.assertEqual(result[0].source_id, target.source_id)

    def test_only_relevant_product_reference_is_appended(self):
        main = fragment("solar.md", "s1", "Солнечные станции > Размещение", "Монтаж на фасаде.")
        solar = fragment("00-reference/02-product-scope-and-limits.md", "s1",
                         "Область применения > Солнечные станции", "Нужен проект.")
        photo = fragment("00-reference/02-product-scope-and-limits.md", "s2",
                         "Область применения > Распознавание по фотографии", "Нужна проверка.")
        results = LexicalRetriever([main, solar, photo]).search("Фасад", 1)
        ids = {f.source_id for f in results}
        self.assertIn(main.source_id, ids)
        self.assertIn(solar.source_id, ids)
        self.assertNotIn(photo.source_id, ids)

    def test_product_constraint_survives_as_companion(self):
        fact = fragment("solar.md", "s1", "Солнечные станции > Размещение", "Монтаж на фасаде.")
        guard = fragment("solar.md", "s2", "Солнечные станции > Чего утверждать нельзя",
                         "Нельзя обещать гарантированную окупаемость.")
        results = LexicalRetriever([fact, guard]).search("Фасад", 1)
        self.assertEqual([f.source_id for f in results], [fact.source_id, guard.source_id])

    def test_multi_product_query_does_not_exclude_either_product(self):
        photo = fragment("photo.md", "s1", "Распознавание по фотографии",
                         "Ручной сбор показаний: фотография прибора.")
        platform = fragment("meter.md", "s1", "Облачная платформа учёта",
                            "Подключенные приборы в бизнес-центре и учёт по арендаторам.")
        other = fragment("solar.md", "s1", "Солнечные станции", "Монтаж оборудования на кровле.")
        results = LexicalRetriever([photo, platform, other]).search(
            "Часть приборов присылают фото, остальные на платформе по арендаторам", 2)
        self.assertEqual({f.source_id for f in results}, {photo.source_id, platform.source_id})

    def test_russian_vocabulary_variants_are_shared(self):
        for left, right, term in [
            ("год выпуска", "год производства", "@manufacture_year"),
            ("техник", "обход контролёров", "@manual_collection"),
            ("воду", "воды", "@water"),
            ("обратно", "вернуться", "@return"),
        ]:
            self.assertIn(term, tokens(left))
            self.assertIn(term, tokens(right))

    def test_explicit_topic_return_does_not_revive_other_product(self):
        solar = fragment("solar.md", "s1", "Солнечные станции > Кровля",
                         "Старая шиферная крыша нуждается в обследовании до установки панелей.")
        meter = fragment("meter.md", "s1", "Облачная платформа учёта > Арендаторы",
                         "Платформа обеспечивает учёт по арендаторам, сбор показаний и кабинет.")
        retriever = LexicalRetriever([solar, meter])
        result = retriever.search("Вернёмся к панелям: на старый шифер можно?\nКонтекст разговора:\n"
                                  "Платформа учёта для арендаторов. Сбор показаний и кабинет.")
        self.assertEqual(result[0].source_id, solar.source_id)

    def test_empty_and_zero_requests_return_no_unrelated_references(self):
        reference = fragment("00-reference/02-product-scope-and-limits.md", "s1",
                             "Область применения > Солнечные станции", "Нужен проект.")
        retriever = LexicalRetriever([reference])
        self.assertEqual(retriever.search(""), [])
        self.assertEqual(retriever.search("Солнечные", 0), [])


if __name__ == "__main__":
    unittest.main()
