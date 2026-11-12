"""Real web proxy -> Go -> Python -> fake OpenAI HTTP server. No external model."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from consultation_http import make_server
from consultant import Consultant
from contracts import Fragment
from llm_client import LLMClient
from retrieval import FixedRetriever
from settings import Settings


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class WebStackTests(unittest.TestCase):
    def test_full_stack_isolation_history_restart_and_outage(self):
        calls = []
        class Model(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                context = json.loads(req['messages'][1]['content'])
                calls.append(context)
                source = context['sources'][0]
                answer = {'answer': 'Тестовый ответ по базе.', 'status': 'answered',
                          'citations': [{'source_id': source['source_id'], 'quote': source['text']}],
                          'contacts': [], 'intent': {}, 'summary': {}}
                body = json.dumps({'choices': [{'message': {'content': json.dumps(answer)}, 'finish_reason': 'stop'}]}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        servers, processes = [], []
        def serve(server):
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            return 'http://127.0.0.1:%d' % server.server_port
        try:
            model_url = serve(ThreadingHTTPServer(('127.0.0.1', 0), Model))
            cfg = Settings(model_url + '/v1', 'test', 'fixture', attempts=1)
            consultant = Consultant(LLMClient(cfg), FixedRetriever([Fragment('test.md', 's1', 'Тестовая база.')]), cfg)
            ml = make_server(('127.0.0.1', 0), consultant)
            ml_url = serve(ml)
            with tempfile.TemporaryDirectory() as tmp:
                binary = str(Path(tmp) / 'api')
                subprocess.run(['go', 'build', '-o', binary, './cmd/api'], cwd=ROOT / 'backend', check=True)
                backend_port = port()
                backend_url = 'http://127.0.0.1:%d' % backend_port
                env = dict(os.environ, BACKEND_ADDR='127.0.0.1:%d' % backend_port,
                           BACKEND_STORE_PATH=str(Path(tmp) / 'sessions.json'), ML_SERVICE_URL=ml_url)
                def start():
                    process = subprocess.Popen([binary], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    processes.append(process)
                    for _ in range(100):
                        try:
                            with urlopen(backend_url + '/health/live', timeout=.1): break
                        except (URLError, OSError): time.sleep(.05)
                    else: self.fail('backend did not start')
                    return process
                process = start()
                spec = importlib.util.spec_from_file_location('web_server', ROOT / 'local-preview/energytool-site/serve.py')
                web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
                class Proxy(web.Handler): backend_url = 'http://127.0.0.1:%d' % backend_port
                web_url = serve(ThreadingHTTPServer(('127.0.0.1', 0), Proxy))
                def api(path, payload=None, post=False):
                    data = json.dumps(payload).encode() if payload is not None else (b'' if post else None)
                    request = Request(web_url + path, data=data, headers={'Content-Type': 'application/json'})
                    with urlopen(request, timeout=5) as response: return json.load(response)
                with urlopen(web_url) as response: self.assertIn(b'/chat.js', response.read())
                self.assertEqual(api('/health/ready')['status'], 'ready')
                first = api('/api/v1/sessions', post=True)['id']
                second = api('/api/v1/sessions', post=True)['id']
                for sid, text in ((first, 'Первый'), (first, 'Продолжение'), (second, 'Другой')):
                    result = api('/api/v1/sessions/' + sid + '/messages', {'content': text})
                    self.assertEqual(result['status'], 'answered')
                    self.assertEqual(result['lead']['session_id'], sid)
                    self.assertEqual(result['sources'][0]['quote'], 'Тестовая база.')
                    self.assertFalse(result['summary']['sent'])
                self.assertEqual([len(c['messages']) for c in calls], [1, 3, 1])
                process.terminate(); process.wait(timeout=5); start()
                history = api('/api/v1/sessions/' + first + '/messages')['messages']
                self.assertEqual(len(history), 4)
                api('/api/v1/sessions/' + first + '/close', post=True)
                with self.assertRaises(HTTPError) as error:
                    api('/api/v1/sessions/' + first + '/messages', {'content': 'После закрытия'})
                self.assertEqual(error.exception.code, 409)
                error.exception.close()
                ml.shutdown(); ml.server_close(); servers.remove(ml)
                result = api('/api/v1/sessions/' + second + '/messages', {'content': 'Сбой'})
                self.assertEqual(result['status'], 'technical_error')
                self.assertEqual(len(api('/api/v1/sessions/' + second + '/messages')['messages']), 4)
        finally:
            for process in processes:
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
            for server in reversed(servers): server.shutdown(); server.server_close()


if __name__ == '__main__':
    unittest.main()
