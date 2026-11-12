import json
import unittest

from contracts import Fragment
from evidence import evidence_catalog, resolve_evidence


def section(document, index, title, body="Текст раздела."):
    return Fragment(document, "s" + str(index), title + "\n" + body)


class CatalogTests(unittest.TestCase):
    def test_every_index_and_leaf_survives_and_documents_are_grouped(self):
        fragments = [section("b.md", 1, "Продукт Б > Применение", "Содержимое Б"),
                     section("a.md", 1, "Продукт А > Стоимость", "Содержимое А"),
                     section("b.md", 2, "Продукт Б > Что мы не делаем", "Ограничение")]
        before = tuple(fragments)
        catalog = evidence_catalog(fragments)
        self.assertEqual(catalog, evidence_catalog(fragments))
        self.assertEqual([row["i"] for row in catalog["sections"]], [0, 1, 2])
        self.assertEqual([row["d"] for row in catalog["sections"]], [0, 1, 0])
        self.assertEqual([row["title"] for row in catalog["sections"]],
                         ["Применение", "Стоимость", "Что мы не делаем"])
        self.assertEqual(catalog["documents"], [{"d": 0, "id": "b.md", "title": "Продукт Б"},
                                                 {"d": 1, "id": "a.md", "title": "Продукт А"}])
        self.assertEqual(tuple(fragments), before)
        json.dumps(catalog, ensure_ascii=False)

    def test_budget_shortens_excerpts_not_titles_or_indices(self):
        fragments = [section("product.md", i, "Продукт > Подробное название раздела " + str(i), "Факт " * 70)
                     for i in range(234)]
        catalog = evidence_catalog(fragments)
        self.assertEqual(len(catalog["sections"]), 234)
        self.assertEqual(catalog["sections"][-1]["i"], 233)
        self.assertEqual(catalog["sections"][-1]["title"], "Подробное название раздела 233")
        self.assertLessEqual(len(json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))), 28000)
        self.assertTrue(all(len(row.get("excerpt", "")) <= 80 for row in catalog["sections"]))

    def test_titles_are_never_discarded_even_when_metadata_exceeds_budget(self):
        fragments = [section("a.md", i, "Корень > " + "Название " * 1000) for i in range(4)]
        catalog = evidence_catalog(fragments)
        self.assertEqual(len(catalog["sections"]), 4)
        self.assertTrue(all("excerpt" not in row for row in catalog["sections"]))
        self.assertEqual(catalog["sections"][3]["title"], fragments[3].text.split("\n")[0].split(" > ")[-1].strip())

    def test_empty_catalog(self):
        self.assertEqual(evidence_catalog([]), {"documents": [], "sections": []})

    def test_introduction_inherits_root_title_without_repeating_it(self):
        catalog = evidence_catalog([section("a.md", 1, "Название продукта", "**Кому:** организациям.")])
        self.assertEqual(catalog["documents"][0]["title"], "Название продукта")
        self.assertEqual(catalog["sections"][0]["title"], "")
        self.assertEqual(catalog["sections"][0]["d"], 0)


class ResolveTests(unittest.TestCase):
    def test_same_document_scope_includes_industrial_and_sales_exclusions(self):
        fragments = [section("losses.md", 1, "Продукт > Что видит пользователь", "Карта объектов."),
                     section("losses.md", 2, "Продукт > Кому подходит > Целевой клиент", "Сетевые организации."),
                     section("losses.md", 3, "Продукт > Не подходит промышленным потребителям", "Иная задача."),
                     section("losses.md", 4, "Продукт > Не подходит энергосбытовым компаниям", "Есть исключение."),
                     section("losses.md", 5, "Продукт > Что мы не делаем", "Не устанавливаем нарушение."),
                     section("losses.md", 6, "Продукт > Чего утверждать нельзя", "Без гарантий."),
                     section("losses.md", 7, "Продукт > Что нужно от клиента", "Большой архив."),
                     section("foreign.md", 1, "Чужой продукт > Кому подходит", "Другая отрасль.")]
        result = resolve_evidence(fragments, [0])
        self.assertEqual(result, fragments[:6])
        self.assertTrue(all(a is b for a, b in zip(result, fragments)))

    def test_whole_bundle_omitted_if_a_guard_does_not_fit(self):
        primary = section("a.md", 1, "А > Описание", "Полезный факт.")
        guard = section("a.md", 2, "А > Ограничения", "Существенное ограничение." * 20)
        self.assertEqual(resolve_evidence([primary, guard], [0], len(primary.text)), [])
        self.assertEqual(resolve_evidence([primary, guard], [0], len(primary.text) + len(guard.text)),
                         [primary, guard])

    def test_primary_order_preserved_across_documents_then_guards(self):
        fragments = [section("a.md", 1, "А > Описание"), section("b.md", 1, "Б > Цена"),
                     section("a.md", 2, "А > Детали"), section("a.md", 3, "А > Кому подходит"),
                     section("b.md", 2, "Б > Что мы не делаем")]
        self.assertEqual(resolve_evidence(fragments, [2, 1, 0]),
                         [fragments[2], fragments[1], fragments[0], fragments[3], fragments[4]])

    def test_all_selected_sections_of_document_share_admission(self):
        fragments = [section("a.md", 1, "А > Описание", "А" * 40),
                     section("b.md", 1, "Б > Описание", "Б"),
                     section("a.md", 2, "А > Детали", "А" * 40),
                     section("a.md", 3, "А > Ограничения", "Важный предел.")]
        budget = len(fragments[0].text) + len(fragments[3].text)
        self.assertEqual(resolve_evidence(fragments, [0, 1, 2], budget), [fragments[1]])

    def test_explicitly_selected_input_section_is_kept_without_duplicates(self):
        fragments = [section("a.md", 1, "А > Что нужно от клиента"),
                     section("a.md", 2, "А > Чего утверждать нельзя")]
        self.assertEqual(resolve_evidence(fragments, [1, 0]), [fragments[1], fragments[0]])

    def test_input_role_is_not_implicitly_added_under_scope_parent(self):
        fragments = [section("a.md", 1, "А > Функции"),
                     section("a.md", 2, "А > Кому подходит > Что нужно от клиента")]
        self.assertEqual(resolve_evidence(fragments, [0]), [fragments[0]])

    def test_normalized_guard_roles(self):
        fragments = [section("a.md", 1, "А > Функции"),
                     section("a.md", 2, "А > **КОМУ НЕ ПОДХОДИТ**"),
                     section("a.md", 3, "А > Важное ограничение по применению"),
                     section("a.md", 4, "А > Целевая аудитория")]
        self.assertEqual(resolve_evidence(fragments, [0]), fragments)

    def test_target_audience_body_marker_is_scope_evidence(self):
        fragments = [section("a.md", 1, "Продукт А > Функции", "Возможность."),
                     section("a.md", 2, "Продукт А", "**Кому:** сетевым организациям.\nОписание."),
                     section("a.md", 3, "Продукт А > Экономика", "Индивидуальный расчёт.")]
        self.assertEqual(resolve_evidence(fragments, [0]), fragments[:2])

    def test_aggregate_reference_title_does_not_add_other_products(self):
        fragments = [section("scope.md", 1, "Область применения продуктов и ограничения > Солнечные станции", "Солнечный профиль."),
                     section("scope.md", 2, "Область применения продуктов и ограничения > Платформа учёта", "Профиль учёта.")]
        self.assertEqual(resolve_evidence(fragments, [0]), [fragments[0]])

    def test_empty_and_zero_budget(self):
        fragments = [section("a.md", 1, "А > Функции")]
        self.assertEqual(resolve_evidence(fragments, []), [])
        self.assertEqual(resolve_evidence([], []), [])
        self.assertEqual(resolve_evidence(fragments, [0], 0), [])

    def test_invalid_selection_is_rejected_not_silently_repaired(self):
        fragments = [section("a.md", i, "А > Раздел") for i in range(12)]
        for indices in ([True], [False], [1.0], ["1"], [-1], [12], [1, 1], list(range(11)), "1", None):
            with self.subTest(indices=indices):
                with self.assertRaises(ValueError):
                    resolve_evidence(fragments, indices)
        for budget in (-1, True, 1.2, "18"):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    resolve_evidence(fragments, [0], budget)


if __name__ == "__main__":
    unittest.main()
