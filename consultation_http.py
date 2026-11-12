"""Internal HTTP adapter for the existing stateless consultation contract."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time

from integration import create_consultant, respond_json
from consultant import parse_payload
from llm_client import ModelError

MAX_BODY = 1 << 20


class WebCitationClient:
    """Select retrieved evidence by ID; resolve quotes before normal validation.

    The map is request-local, so citations cannot leak across sessions. This
    establishes provenance, not semantic entailment of the generated answer.
    """
    def __init__(self, client):
        self.client = client

    def complete(self, messages, *, deadline=None):
        context = json.loads(messages[1]['content'])
        evidence = {}
        for index, source in enumerate(context['sources']):
            evidence_id = 'E%d' % (index + 1)
            source['evidence_id'] = evidence_id
            evidence[evidence_id] = source
        instruction = (
            '\nВ веб-интерфейсе формат citations заменён: '
            '[{"source_id":"точный source_id","evidence_id":"E1"}]. '
            'Выбирай evidence_id из sources только для фрагментов, подтверждающих ответ. '
            'Не генерируй поле quote: сервер подставит дословный текст выбранного фрагмента. '
            'Остальные поля JSON сохраняются. Ответ клиенту — кратко, обычно 40–100 слов. '
            'Не копируй тексты источников в summary. Контакты и сведения клиента '
            'по-прежнему требуют дословного quote из messages.'
        )
        prepared = [dict(message) for message in messages]
        prepared[0]['content'] += instruction
        prepared[1]['content'] = json.dumps(context, ensure_ascii=False)
        raw = self.client.complete(prepared, deadline=deadline)
        try:
            payload = parse_payload(raw)
        except ModelError:
            return raw  # Preserve the consultant's schema-repair attempt.
        for citation in payload['citations']:
            if 'evidence_id' not in citation:
                continue  # Legacy exact quotes still go through the normal validator.
            evidence_id = citation.pop('evidence_id')
            source = evidence.get(evidence_id) if isinstance(evidence_id, str) else None
            if source is None or citation.get('source_id') != source['source_id']:
                raise ModelError('ungrounded_citation', retryable=True)
            citation['quote'] = source['text']
        return json.dumps(payload, ensure_ascii=False)


def make_server(address, consultant, *, workers=3, budget=240):
    slots = threading.BoundedSemaphore(workers)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass  # Do not log questions, contacts, keys, or upstream error details.

        def reply(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path in ('/health/live', '/health/ready'):
                self.reply(200, {'status': 'ready'})
            else:
                self.reply(404, {'error': 'not_found'})

        def do_POST(self):
            if self.path != '/respond':
                return self.reply(404, {'error': 'not_found'})
            if self.headers.get('Transfer-Encoding'):
                return self.reply(400, {'error': 'unsupported_transfer_encoding'})
            try:
                size = int(self.headers.get('Content-Length', '-1'))
            except ValueError:
                size = -1
            if size < 0:
                return self.reply(411, {'error': 'content_length_required'})
            if size > MAX_BODY:
                return self.reply(413, {'error': 'body_too_large'})
            if self.headers.get_content_type() != 'application/json':
                return self.reply(415, {'error': 'json_required'})
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError()
                payload = json.loads(raw)
            except (ValueError, UnicodeError, TimeoutError):
                return self.reply(400, {'error': 'invalid_json'})
            if not slots.acquire(blocking=False):
                return self.reply(503, {'error': 'busy'})
            try:
                result = respond_json(consultant, payload, deadline=time.monotonic() + budget)
            except (ValueError, TypeError):
                self.reply(400, {'error': 'invalid_request'})
            except Exception:
                self.reply(500, {'error': 'consultation_failed'})
            else:
                self.reply(200, result)
            finally:
                slots.release()

    return ThreadingHTTPServer(address, Handler)


def main():
    knowledge = Path(os.getenv('KNOWLEDGE_ZIP', str(Path(os.getenv('DATA_DIR', 'data')) / 'knowledge-base.zip')))
    try:
        consultant = create_consultant(knowledge)
        consultant.client = WebCitationClient(consultant.client)
        budget = float(os.getenv('ML_REQUEST_BUDGET', '240'))
        if not 0 < budget <= 300:
            raise ValueError('invalid request budget')
        server = make_server((os.getenv('ML_HTTP_HOST', '127.0.0.1'), int(os.getenv('ML_HTTP_PORT', '8090'))),
                             consultant, workers=consultant.settings.workers, budget=budget)
    except Exception:
        raise SystemExit('ML startup failed: check model environment, knowledge ZIP and HTTP configuration') from None
    print('Consultation HTTP service ready', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
