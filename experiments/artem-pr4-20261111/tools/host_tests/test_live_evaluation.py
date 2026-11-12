"""Host-only orchestration tests, explicitly included by tools/check_all.py.

The live harness must reject technical fallbacks even in a valid CSV. These
tests exercise developer tools and are kept out of the runtime container suite.
"""
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from zipfile import ZipFile

from tools.build_submission import build

ROOT = Path(__file__).resolve().parents[2]


class LiveEvaluationTests(unittest.TestCase):
    def run_harness(self, status):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                payload = ({'choices': [{'message': {'content': 'Проверочный ответ.'},
                                         'finish_reason': 'stop'}],
                            'usage': {'prompt_tokens': 1, 'completion_tokens': 2}}
                           if status == 200 else {'error': 'temporary failure'})
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                build(folder / 'candidate.zip')
                with (folder / 'questions.csv').open('w', encoding='utf8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['id', 'question'])
                    writer.writerow(['probe', 'Что умеет сервис?'])
                with ZipFile(folder / 'kb.zip', 'w') as archive:
                    archive.writestr('guide.md', '# Сервис\nСервис показывает расход энергии.')
                env = {'PATH': os.environ.get('PATH', ''), 'PYTHONIOENCODING': 'utf8',
                       'LLM_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1',
                       'LLM_API_KEY': 'test-not-a-secret', 'LLM_MODEL': 'mock',
                       'MAX_WORKERS': '1', 'LLM_TIMEOUT': '2', 'LLM_ATTEMPTS': '1',
                       # This mock tests chat transport; hybrid faults have a separate suite.
                       'RETRIEVAL_MODE': 'a2',
                       'RUN_BUDGET_SECONDS': '20'}
                result = subprocess.run([
                    sys.executable, str(ROOT / 'tools/evaluate_zip_live.py'),
                    '--zip', str(folder / 'candidate.zip'), '--questions', str(folder / 'questions.csv'),
                    '--kb', str(folder / 'kb.zip'), '--output', str(folder / 'output'),
                    '--model-label', 'instrumentation mock; not a real model',
                ], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30)
                summary = json.loads((folder / 'output/summary.json').read_text())
                calls = [json.loads(line) for line in
                         (folder / 'output/api-observations.jsonl').read_text().splitlines()]
                return result, summary, calls
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_complete_generation_records_provenance_and_resources(self):
        process, summary, calls = self.run_harness(200)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(summary['csv_valid'])
        self.assertTrue(summary['generation_complete'])
        self.assertGreater(summary['resource_usage']['max_rss_raw'], 0)
        self.assertEqual(len(calls[0]['request_sha256']), 64)

    def test_valid_csv_with_transport_failure_does_not_pass(self):
        process, summary, _ = self.run_harness(503)
        self.assertNotEqual(process.returncode, 0)
        self.assertTrue(summary['csv_valid'])
        self.assertFalse(summary['generation_complete'])
        self.assertEqual(summary['http_failures'], 1)


if __name__ == '__main__':
    unittest.main()
