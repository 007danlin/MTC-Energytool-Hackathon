"""Real proxy -> Go -> controlled slow HTTP ML; no external model or user data."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class WaitRecoveryStackTests(unittest.TestCase):
    def test_disconnect_handoff_restart_and_resume(self):
        starts = {text: threading.Event() for text in ('slow', 'restart')}
        gates = {text: threading.Event() for text in starts}
        calls = []

        class SlowML(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, data):
                body = json.dumps(data).encode()
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The restart scenario deliberately kills the caller.

            def do_GET(self):
                self.reply({'status': 'ready'})

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(request)
                latest = request['messages'][-1]['content']
                if latest in gates:
                    starts[latest].set()
                    if not gates[latest].wait(15):
                        return
                self.reply({
                    'schema_version': '1.0', 'status': 'answered', 'answer': 'Контролируемый ответ: ' + latest,
                    'lead': {'session_id': request['session_id'], 'fields': {}, 'evidence': {}},
                    'sources': [], 'summary': {}, 'debug': {}, 'elapsed_ms': 10,
                })

        servers, processes, connections = [], [], []

        def serve(server):
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            return 'http://127.0.0.1:%d' % server.server_port

        try:
            ml_url = serve(ThreadingHTTPServer(('127.0.0.1', 0), SlowML))
            with tempfile.TemporaryDirectory() as tmp:
                binary = str(Path(tmp) / 'api')
                subprocess.run(['go', 'build', '-o', binary, './cmd/api'], cwd=ROOT / 'backend', check=True)
                backend_port = unused_port()
                backend_url = 'http://127.0.0.1:%d' % backend_port
                env = dict(os.environ, BACKEND_ADDR='127.0.0.1:%d' % backend_port,
                           BACKEND_STORE_PATH=str(Path(tmp) / 'sessions.json'), ML_SERVICE_URL=ml_url,
                           EXPERT_KB_SNAPSHOT=str(Path(tmp) / 'expert-kb.json'))

                def start_backend():
                    process = subprocess.Popen([binary], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    processes.append(process)
                    for _ in range(100):
                        try:
                            with urlopen(backend_url + '/health/live', timeout=.1):
                                return process
                        except (URLError, OSError):
                            time.sleep(.02)
                    self.fail('backend did not start')

                process = start_backend()
                spec = importlib.util.spec_from_file_location('recovery_web', ROOT / 'local-preview/energytool-site/serve.py')
                web = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(web)

                class Proxy(web.Handler):
                    backend_url = 'http://127.0.0.1:%d' % backend_port

                web_server = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
                web_url = serve(web_server)

                def api(path, payload=None, post=False):
                    data = json.dumps(payload).encode() if payload is not None else (b'' if post else None)
                    request = Request(web_url + path, data=data, headers={'Content-Type': 'application/json'})
                    with urlopen(request, timeout=3) as response:
                        return json.load(response)

                def disconnect_message(sid, text, rid):
                    connection = http.client.HTTPConnection('127.0.0.1', web_server.server_port, timeout=3)
                    connections.append(connection)
                    connection.request('POST', '/api/v1/sessions/' + sid + '/messages',
                                       body=json.dumps({'content': text, 'client_request_id': rid}),
                                       headers={'Content-Type': 'application/json'})
                    self.assertTrue(starts[text].wait(3), 'request did not reach slow ML')
                    connection.close()  # Browser AbortController / tab navigation.

                sid = api('/api/v1/sessions', post=True)['id']
                prefix = '/api/v1/sessions/' + sid
                disconnect_message(sid, 'slow', 'slow-id')
                pending = api(prefix)
                self.assertTrue(pending['requests']['slow-id']['pending'])
                self.assertEqual(len(pending['messages']), 1)
                with self.assertRaises(HTTPError) as error:
                    api(prefix + '/requests/slow-id')
                self.assertEqual(error.exception.code, 409)
                self.assertEqual(json.load(error.exception)['code'], 'request_pending')
                error.exception.close()

                started = time.monotonic()
                saved = api(prefix + '/application', {'client_request_id': 'handoff-id',
                            'email': 'slow@example.test', 'summary': 'Связаться по вопросу учёта'})
                self.assertLess(time.monotonic() - started, 1, 'operator handoff waited for ML')
                self.assertEqual(saved['application']['email'], 'slow@example.test')
                self.assertFalse(gates['slow'].is_set())
                self.assertTrue(api(prefix)['requests']['slow-id']['pending'])

                gates['slow'].set()
                for _ in range(100):
                    completed = api(prefix)
                    if not completed['requests']['slow-id'].get('pending'):
                        break
                    time.sleep(.02)
                else:
                    self.fail('completed response did not settle')
                self.assertEqual(len(completed['messages']), 2)
                self.assertEqual(completed['messages'][1]['response']['request_id'], 'slow-id')
                self.assertEqual(completed['application']['email'], 'slow@example.test')
                self.assertEqual(api(prefix + '/requests/slow-id')['status'], 'answered')
                replay = api(prefix + '/messages', {'content': 'slow', 'client_request_id': 'slow-id'})
                self.assertEqual(replay['status'], 'answered')
                self.assertEqual(len(calls), 1, 'replay regenerated the answer')

                disconnect_message(sid, 'restart', 'restart-id')
                self.assertTrue(api(prefix)['requests']['restart-id']['pending'])
                process.kill()
                process.wait(timeout=3)
                process = start_backend()
                recovered = api(prefix)
                self.assertEqual(recovered['last_result']['status'], 'technical_error')
                self.assertEqual(recovered['last_result']['debug']['error_code'], 'request_interrupted')
                self.assertEqual(recovered['last_result']['request_id'], 'restart-id')
                self.assertEqual(len(recovered['messages']), 4)
                self.assertEqual(len(api(prefix)['messages']), 4, 'read repeated the recovery message')
                self.assertEqual(api(prefix + '/requests/restart-id')['status'], 'technical_error')
                self.assertEqual(recovered['application']['email'], 'slow@example.test')
                gates['restart'].set()

                closed = api(prefix + '/close', post=True)
                self.assertEqual(closed['status'], 'closed')
                resumed = api(prefix + '/resume', post=True)
                self.assertEqual(resumed['status'], 'active')
                self.assertNotIn('closed_at', resumed)
                self.assertEqual(len(resumed['messages']), 4)
                continued = api(prefix + '/messages', {'content': 'continue', 'client_request_id': 'continue-id'})
                self.assertEqual(continued['status'], 'answered')
                final = api(prefix)
                self.assertEqual(len(final['messages']), 6)
                self.assertEqual(final['application']['email'], 'slow@example.test')
                self.assertEqual(len(calls[-1]['messages']), 5)
                self.assertEqual([c['messages'][-1]['content'] for c in calls], ['slow', 'restart', 'continue'])
        finally:
            for gate in gates.values():
                gate.set()
            for connection in connections:
                connection.close()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=12)
            for server in reversed(servers):
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
