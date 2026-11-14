"""The web path uses the organizer's documented OpenAI-compatible contract."""
import json,tempfile,threading,unittest
from pathlib import Path
from zipfile import ZipFile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from settings import Settings
from integration import create_consultant,respond_json
from consultation_http import WebCitationClient

class OrganizerWebTests(unittest.TestCase):
 def test_official_aliases_reach_web_model_without_ollama_extensions(self):
  seen=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
    seen.append((self.path,self.headers.get('Authorization'),body))
    answer={'answer':'Для склада сначала уточните способ снятия показаний.','status':'clarification','citations':[{'evidence_id':'E1'}],'contacts':[],'intent':{},'summary':{}}
    raw=json.dumps({'choices':[{'message':{'content':json.dumps(answer,ensure_ascii=False)},'finish_reason':'stop'}]}).encode()
    self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  with tempfile.TemporaryDirectory() as tmp:
   kb=Path(tmp)/'kb.zip'
   with ZipFile(kb,'w') as z:z.writestr('warehouse.md','# Склад\n\nУточните способ снятия показаний.')
   for url,key,model in [('LLM_BASE_URL','LLM_API_KEY','LLM_MODEL'),('OPENAI_BASE_URL','OPENAI_API_KEY','OPENAI_MODEL'),('BASE_URL','OPENAI_API_KEY','GEN_MODEL')]:
    cfg=Settings.from_env({url:f'http://127.0.0.1:{server.server_port}/v1',key:'organizer-test-key',model:'organizer-model-from-env','MAX_TOKENS':'1536','TEMPERATURE':'0.2'})
    svc=create_consultant(kb,settings=cfg,retrieval_mode='n2');svc.client=WebCitationClient(svc.client)
    result=respond_json(svc,{'session_id':'s1','messages':[{'role':'user','content':'Есть склад. Как наладить учёт?'}]})
    self.assertNotEqual(result['status'],'technical_error')
    path,auth,body=seen[-1];self.assertEqual(path,'/v1/chat/completions');self.assertEqual(auth,'Bearer organizer-test-key');self.assertEqual(body['model'],'organizer-model-from-env')
    self.assertEqual(set(body),{'model','messages','max_tokens','temperature'});self.assertEqual(body['max_tokens'],1536)
    self.assertTrue(result['sources']);self.assertNotIn('ollama',json.dumps(body).lower())
