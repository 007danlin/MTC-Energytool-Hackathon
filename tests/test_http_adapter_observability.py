import json
import unittest
from unittest.mock import patch

import consultation_http


class _Settings:
    model = "test-model"


class _Consultant:
    settings = _Settings()


class AdapterObservabilityTests(unittest.TestCase):
    def test_version_is_stable_and_debug_fields_are_added_by_handler_path(self):
        self.assertRegex(consultation_http.WEB_ADAPTER_VERSION, r"^\d+\.\d+\.\d+$")
        result = {"answer": "ok", "status": "answered", "elapsed_ms": 17}
        started = 100.0
        with patch.object(consultation_http.time, "monotonic", return_value=started + 0.123):
            debug = result.setdefault("debug", {})
            debug["adapter_version"] = consultation_http.WEB_ADAPTER_VERSION
            debug["model"] = _Consultant.settings.model
            debug["consultation_elapsed_ms"] = int((consultation_http.time.monotonic() - started) * 1000)
            debug["generation_elapsed_ms"] = result.get("elapsed_ms", debug["consultation_elapsed_ms"])
            debug["final_status"] = result.get("status")
        self.assertEqual(result["debug"]["adapter_version"], "1.1.0")
        self.assertEqual(result["debug"]["model"], "test-model")
        self.assertEqual(result["debug"]["consultation_elapsed_ms"], 123)
        self.assertEqual(result["debug"]["generation_elapsed_ms"], 17)
        self.assertEqual(result["debug"]["final_status"], "answered")


if __name__ == "__main__":
    unittest.main()