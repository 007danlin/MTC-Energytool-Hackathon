import json
import unittest
from grounded_edit import apply_edits


class GroundedEditTests(unittest.TestCase):
    def setUp(self):
        self.answer = "Да. Минимальный архив — 18 месяцев. Почасовые данные желательны."
        self.sources = [{"source_id": "doc#s009", "text": "Глубина архива — не менее одного года. Почасовые данные желательны."}]
        self.patch = {"before": "Минимальный архив — 18 месяцев.",
                      "after": "Минимальный архив — один год.", "source_id": "doc#s009",
                      "quote": "Глубина архива — не менее одного года."}

    def apply(self, patches):
        return apply_edits(self.answer, json.dumps({"patches": patches}, ensure_ascii=False), self.sources)

    def test_verified_local_edit_preserves_surrounding_answer(self):
        answer, d = self.apply([self.patch])
        self.assertEqual(answer, "Да. Минимальный архив — один год. Почасовые данные желательны.")
        self.assertEqual(d, {"edit_status": "patched", "edits": 1})

    def test_no_edit_is_byte_exact(self):
        self.assertEqual(self.apply([])[0], self.answer)

    def test_invalid_or_non_json_keeps_complete_answer(self):
        for raw in ["", "Ответ хороший", "null", "[]", '{"patches":null}', '{"patches":[],"answer":"x"}']:
            with self.subTest(raw=raw):
                self.assertEqual(apply_edits(self.answer, raw, self.sources)[0], self.answer)

    def test_unknown_source_or_changed_quote_rejected(self):
        for change in [{"source_id": "other#s001"}, {"quote": "Минимальный архив — полгода."}]:
            answer, d = self.apply([{**self.patch, **change}])
            self.assertEqual(answer, self.answer)
            self.assertEqual(d["edit_status"], "invalid_evidence")

    def test_new_number_needs_cited_evidence(self):
        answer, d = self.apply([{**self.patch, "after": "Минимальный архив — 6 месяцев."}])
        self.assertEqual(answer, self.answer)
        self.assertEqual(d["edit_status"], "unsupported_new_number")

    def test_repeated_or_nonliteral_target_rejected(self):
        for before in ["Архив не меньше 18 месяцев.", "."]:
            self.assertEqual(self.apply([{**self.patch, "before": before}])[0], self.answer)

    def test_overlapping_edits_reject_whole_patch_set(self):
        short = {**self.patch, "before": "18 месяцев", "after": "один год"}
        answer, d = self.apply([self.patch, short])
        self.assertEqual(answer, self.answer)
        self.assertEqual(d["edit_status"], "overlapping_edits")

    def test_whitespace_normalization_does_not_require_rewriting_source(self):
        source = [{"source_id": "doc#s009", "text": "Глубина архива — не менее\nодного года. Почасовые данные желательны."}]
        answer, d = apply_edits(self.answer, json.dumps({"patches": [self.patch]}), source)
        self.assertEqual(d["edit_status"], "patched")

    def test_deleting_entire_answer_rejected(self):
        self.assertEqual(self.apply([{**self.patch, "before": self.answer, "after": ""}])[0], self.answer)

    def test_edits_apply_to_original_spans(self):
        other = {**self.patch, "before": "Почасовые данные желательны.", "after": "Почасовые записи желательны.",
                 "quote": "Почасовые данные желательны."}
        answer, d = self.apply([other, self.patch])
        self.assertEqual(d["edits"], 2)
        self.assertIn("Почасовые записи", answer)


if __name__ == "__main__":
    unittest.main()
