"""Paired local regression comparison; isolated from the concurrent retrieval experiment."""
import ast,hashlib,json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import consultant
from consultant import Consultant
from contracts import ConsultationRequest
from dialogue import parse_question
from llm_client import LLMClient,HTTPTransport
from retrieval import LexicalRetriever
from settings import Settings
OUT=ROOT/'reports/private/a4-prompt-20261111'
BASE=consultant.ANSWER_PROMPT
node=ast.parse((Path(__file__).parent/'prompts.py').read_text())
NEW=next(ast.literal_eval(n.value) for n in node.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ANSWER_PROMPT' for t in n.targets))
cases=json.loads((OUT/'cases.json').read_text())
results_path=OUT/'answers.json'
results=json.loads(results_path.read_text()) if results_path.exists() else {}
class Capture(HTTPTransport):
 def post(self,url,headers,payload,timeout):
  self.payload=json.loads(payload); self.sha=hashlib.sha256(payload).hexdigest()
  status,hs,body=super().post(url,headers,payload,timeout)
  self.response=json.loads(body);return status,hs,body
cfg=Settings('http://127.0.0.1:11434/v1','local-no-secret','energytool-qwen-local-eval:20261110',workers=1,timeout=300,attempts=1)
retriever=LexicalRetriever.from_zip(ROOT/'data/knowledge-base.zip')
rng=random.Random(20261111)
for case in cases:
 variants=['A2','A4'];rng.shuffle(variants)
 for variant in variants:
  key=case['id']+':'+variant
  if key in results: continue
  consultant.ANSWER_PROMPT=BASE if variant=='A2' else NEW
  capture=Capture();service=Consultant(LLMClient(cfg,capture),retriever,cfg)
  result=service.respond(ConsultationRequest(key,parse_question(case['question'])),answer_only=True)
  record={'answer':result.answer,'status':result.status,'elapsed_ms':result.elapsed_ms,'debug':result.debug,'request_sha256':getattr(capture,'sha',None),'request':getattr(capture,'payload',None),'usage':getattr(capture,'response',{}).get('usage'), 'finish_reason':getattr(capture,'response',{}).get('choices',[{}])[0].get('finish_reason')}
  results[key]=record
  results_path.write_text(json.dumps(results,ensure_ascii=False,indent=2))
  print(key,result.status,result.elapsed_ms,flush=True)
print('DONE',len(results),flush=True)
