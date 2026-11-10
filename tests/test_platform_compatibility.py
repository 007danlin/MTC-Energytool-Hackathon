"""Regressions for startup/API mismatches uncovered after the scoring failure."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import warnings

from consultant import Consultant
from contracts import ConsultationRequest, Message
from llm_client import HTTPTransport, LLMClient, ModelError
from retrieval import FixedRetriever
from settings import Settings
from solution import find_inputs, read_questions, run

BASE = {"LLM_BASE_URL": "http://localhost/v1", "LLM_API_KEY": "not-a-real-key", "LLM_MODEL": "provided-model"}


class PlatformConfigTests(unittest.TestCase):
    def test_unbounded_positive_generation_budget_is_forwarded(self):
        for value in (64, 32768):
            cfg = Settings.from_env({**BASE, "MAX_TOKENS": str(value)})
            self.assertEqual(cfg.max_tokens, value)

    def test_resource_settings_clamped_instead_of_aborting(self):
        with warnings.catch_warnings(record=True) as records:
            cfg = Settings.from_env({**BASE, "MAX_WORKERS": "16", "TOP_K": "50"})
        self.assertEqual((cfg.workers, cfg.top_k), (8, 40))
        self.assertEqual(len(records), 2)

    def test_invalid_optional_values_use_defaults_without_echoing_secrets(self):
        with warnings.catch_warnings(record=True) as records:
            cfg = Settings.from_env({**BASE, "MAX_TOKENS": "private-value", "TEMPERATURE": "nan"})
        self.assertEqual((cfg.max_tokens, cfg.temperature), (2048, 0.0))
        self.assertNotIn("private-value", str([r.message for r in records]))

    def test_official_alias_takes_precedence_over_legacy_base(self):
        cfg = Settings.from_env({**BASE, "BASE_URL": "http://legacy.invalid/v1"})
        self.assertEqual(cfg.base_url, BASE["LLM_BASE_URL"])

    def test_csv_columns_matched_by_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "questions.csv"
            for content in ("question,id\nВопрос,001\n", "extra,id,question\nmetadata,001,Вопрос\n"):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(read_questions(path), [("001", "Вопрос")])

    def test_sample_input_aliases_and_script_relative_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / "platform-data"
            data.mkdir()
            (data / "train.csv").touch()
            (data / "kb.zip").touch()
            with patch("solution.__file__", str(root / "solution.py")):
                self.assertEqual(find_inputs("platform-data"), ((data / "train.csv").resolve(), (data / "kb.zip").resolve()))

    def test_checkpoint_written_before_any_api_call(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "submission.csv"
            class FailingClient:
                def complete(inner, messages, deadline=None):
                    self.assertTrue(path.is_file())
                    self.assertIn("001", path.read_text())
                    raise ModelError("api_error", status=401)
            cfg = Settings.from_env(BASE)
            service = Consultant(FailingClient(), FixedRetriever([]), cfg)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                statuses = run([("001", "Вопрос")], service, cfg, path)
            self.assertEqual(statuses, ["api_error"])
            self.assertIn('"http_status": 401', stderr.getvalue())
            self.assertNotIn("not-a-real-key", stderr.getvalue())

    def test_truncated_completion_not_repeated_with_identical_token_limit(self):
        class TruncatedTransport:
            calls = 0
            def post(inner, *args):
                inner.calls += 1
                return 200, {}, b'{"choices":[{"finish_reason":"length","message":{"content":"partial"}}]}'
        transport = TruncatedTransport()
        with self.assertRaises(ModelError) as caught:
            LLMClient(Settings.from_env(BASE), transport).complete([])
        self.assertEqual(caught.exception.code, "truncated_response")
        self.assertEqual(transport.calls, 1)


class PlatformHTTPTests(unittest.TestCase):
    def start_server(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.addCleanup(cleanup)
        return server

    def test_real_http_uses_provided_model_url_key_and_parameters(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *args):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.path, self.headers.get("Authorization"), payload))
                body = json.dumps({"choices": [{"message": {"content": "Ответ модели"}, "finish_reason": "stop"}]}, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
        server = self.start_server(Handler)
        for base_name in ("LLM_BASE_URL", "OPENAI_BASE_URL", "BASE_URL"):
            cfg = Settings.from_env({base_name: f"http://127.0.0.1:{server.server_port}/v1/",
                                     "OPENAI_API_KEY": "fixture-key", "GEN_MODEL": "organizer-model",
                                     "MAX_TOKENS": "32768", "TEMPERATURE": "0.3"})
            answer = LLMClient(cfg).complete([{"role": "user", "content": "Русский вопрос"}])
            self.assertEqual(answer, "Ответ модели")
            endpoint, auth, payload = seen[-1]
            self.assertEqual(endpoint, "/v1/chat/completions")
            self.assertEqual(auth, "Bearer fixture-key")
            self.assertEqual((payload["model"], payload["max_tokens"], payload["temperature"]), ("organizer-model", 32768, 0.3))
            self.assertEqual(payload["messages"][0]["content"], "Русский вопрос")

    def test_connection_close_body_obeys_remaining_deadline(self):
        class SlowHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                time.sleep(0.25)
                self.send_response(200)
                self.send_header("Connection", "close")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.flush()
                time.sleep(0.3)
                try:
                    self.wfile.write(b"{}")
                except OSError:
                    pass
        server = self.start_server(SlowHandler)
        start = time.monotonic()
        with self.assertRaises(OSError):
            HTTPTransport().post(f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                                 {"Content-Type": "application/json"}, b"{}", 0.4)
        self.assertLess(time.monotonic() - start, 0.53)


if __name__ == "__main__":
    unittest.main()
