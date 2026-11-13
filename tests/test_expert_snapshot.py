import json
import tempfile
import unittest
from pathlib import Path

from retrieval import load_expert_snapshot


class ExpertSnapshotTests(unittest.TestCase):
    def write(self, payload):
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
        json.dump(payload, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_loads_one_stable_fragment_and_version(self):
        path = self.write({"kb_version": "web-7", "documents": [{
            "entry_id": "kb-1", "revision": 2, "path": "90-expert/kb-1-r2.md",
            "source_id": "90-expert/kb-1-r2.md#s001",
            "markdown": "# Ответ специалиста: Тест\n\nВопрос: Как?\n\nОтвет: Делайте так.\n\nПрименимо: Для теста.\n\nОснование: Проверено.",
            "test": True,
        }]})
        version, fragments = load_expert_snapshot(path)
        self.assertEqual(version, "web-7")
        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].source_id, "90-expert/kb-1-r2.md#s001")

    def test_rejects_private_or_unknown_fields(self):
        path = self.write({"kb_version": "web-8", "documents": [{
            "entry_id": "kb-1", "revision": 1, "path": "90-expert/kb-1-r1.md",
            "source_id": "90-expert/kb-1-r1.md#s001", "markdown": "# x\n\ntext",
            "session_id": "private",
        }]})
        with self.assertRaises(ValueError):
            load_expert_snapshot(path)


if __name__ == "__main__":
    unittest.main()