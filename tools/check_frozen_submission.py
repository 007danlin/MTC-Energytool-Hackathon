"""Run immutable N2 ZIP with organizer-style environment against a local API fixture."""
import csv,hashlib,json,os,subprocess,sys,tempfile,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
archive=ROOT/'artifacts/mts-energytool-n2-docs.zip'
expected='a22d786f895257e14fb89e747a674cd419be0d711ed43b834fb9442ef3b6ac9b'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected,'Frozen submission changed'
calls=[]
class API(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(body)
  assert self.path=='/v1/chat/completions';assert self.headers['Authorization']=='Bearer organizer-test-key';assert body['model']=='organizer-model-id'
  reply=json.dumps({'choices':[{'message':{'content':'[MOCK] Проверка интерфейса модели, не качество консультации.'},'finish_reason':'stop'}]}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(reply)));self.end_headers();self.wfile.write(reply)
server=ThreadingHTTPServer(('127.0.0.1',0),API);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 for names in [('LLM_BASE_URL','LLM_API_KEY','LLM_MODEL'),('OPENAI_BASE_URL','OPENAI_API_KEY','OPENAI_MODEL'),('BASE_URL','OPENAI_API_KEY','GEN_MODEL')]:
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)
   with ZipFile(archive) as z:
    assert z.testzip() is None
    assert all('/' not in n for n in z.namelist())
    z.extractall(p)
   (p/'knowledge-base.zip').write_bytes((ROOT/'data/knowledge-base.zip').read_bytes())
   with (p/'questions.csv').open('w') as f:
    w=csv.writer(f);w.writerow(['id','question']);w.writerow(['001','Здравствуйте!\nКак автоматизировать показания счётчиков?']);w.writerow(['002','Хочу поговорить со специалистом.'])
   env={'PATH':os.environ['PATH'],'PYTHONIOENCODING':'utf-8','DATA_DIR':str(p),'MAX_WORKERS':'1','LLM_ATTEMPTS':'1','LLM_TIMEOUT':'10',names[0]:'http://127.0.0.1:%s/v1'%server.server_port,names[1]:'organizer-test-key',names[2]:'organizer-model-id'}
   subprocess.run([sys.executable,'solution.py'],cwd=p,env=env,check=True,timeout=35,capture_output=True)
   rows=list(csv.DictReader((p/'submission.csv').open()))
   assert [r['id']for r in rows]==['001','002'];assert all(r['answer'].startswith('[MOCK]')for r in rows)
 assert len(calls)==6
 report={'passed':True,'sha256':expected,'zip_root_layout':True,'environment_variants':3,'http_requests':len(calls),'model':'organizer-model-id (fixture)','real_organizer_api_called':False}
 path=ROOT/'reports/release-validation/frozen-model-contract.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:server.shutdown();server.server_close()
