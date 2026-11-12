import json
import threading
import unittest
import urllib.error
import urllib.request

from consultation_http import make_server, MAX_BODY, WebCitationClient
from llm_client import ModelError
from consultant import Consultant
from contracts import Fragment
from retrieval import FixedRetriever
from settings import Settings
from tests.test_core import ScriptedClient, payload, FRAGMENT


class HTTPAdapterTests(unittest.TestCase):
    def setUp(self):
        service = Consultant(ScriptedClient(payload()), FixedRetriever([FRAGMENT]),
                             Settings('http://unused', 'test', 'test'))
        self.server = make_server(('127.0.0.1', 0), service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path='/respond', payload=None, headers=None):
        request = urllib.request.Request(self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers or {'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_contract_and_health(self):
        self.assertEqual(self.request('/health/ready')[0], 200)
        status, result = self.request(payload={'session_id': 's1', 'messages': [{'role': 'user', 'content': 'Вопрос'}], 'lead': None})
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['lead']['session_id'], 's1')
        self.assertEqual(result['sources'][0]['quote'], FRAGMENT.text)
        self.assertFalse(result['summary']['sent'])

    def test_invalid_input_and_session_mismatch(self):
        for value in ([], {}, {'session_id': 's1', 'messages': [{'role': 'system', 'content': 'x'}]},
                      {'session_id': 's1', 'messages': [{'role': 'user', 'content': 'x'}], 'lead': {'session_id': 'other'}}):
            self.assertEqual(self.request(payload=value)[0], 400)
        self.assertEqual(self.request('/missing')[0], 404)
        self.assertEqual(self.request(payload={}, headers={'Content-Type': 'application/json', 'Content-Length': str(MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.request(payload={}, headers={'Content-Type': 'text/plain'})[0], 415)



class WebCitationTests(unittest.TestCase):
    def test_selected_evidence_is_exact_and_request_local(self):
        class Client:
            def complete(self, messages, **kwargs):
                context = json.loads(messages[1]['content'])
                source = context['sources'][0]
                result = payload()
                result['citations'] = [{'source_id': source['source_id'], 'evidence_id': source['evidence_id']}]
                return json.dumps(result)
        client = WebCitationClient(Client())
        for text in ('Точный первый фрагмент.', 'Другой фрагмент второй сессии.'):
            messages = [{'role':'system','content':'Rules'}, {'role':'user','content':json.dumps({'sources':[{'source_id':'doc#s1','text':text}]})}]
            result = json.loads(client.complete(messages))
            self.assertEqual(result['citations'], [{'source_id':'doc#s1','quote':text}])
            self.assertNotIn('evidence_id', messages[1]['content'])

    def test_unknown_or_mismatched_evidence_is_rejected(self):
        for citation in ({'source_id':'doc#s1','evidence_id':'E999'}, {'source_id':'wrong','evidence_id':'E1'}, {'source_id':'doc#s1','evidence_id':[]}):
            result = payload()
            result['citations'] = [citation]
            client = WebCitationClient(ScriptedClient(result))
            messages = [{'role':'system','content':'Rules'}, {'role':'user','content':json.dumps({'sources':[{'source_id':'doc#s1','text':'Exact evidence text.'}]})}]
            with self.assertRaises(ModelError):
                client.complete(messages)


if __name__ == '__main__':
    unittest.main()
