import json,unittest
from pathlib import Path
from consultant import Consultant
import consultant
from prompts import ANSWER_PROMPT,answer_prompt
from contracts import ConsultationRequest
from dialogue import parse_question
from retrieval import LexicalRetriever
from settings import Settings
ROOT=Path(__file__).resolve().parents[2]
class Capture:
 def complete(self,messages,**kwargs):
  self.messages=messages
  return 'Проверка запроса.'
class CandidateTests(unittest.TestCase):
 def test_application_fields_and_other_turns(self):
  for text in ['Мой телефон +7 900 123-45-67. Подготовьте заявку.','Пишите на test@example.org','Телефон не дам, заявку не хочу.']:
   self.assertNotEqual(answer_prompt(parse_question(text)),ANSWER_PROMPT)
  for text in ['Мощность 900 кВт, какая категория?','Насколько быстро собираются показания?','Что такое небаланс?']:
   self.assertEqual(answer_prompt(parse_question(text)),ANSWER_PROMPT)
 def test_organizer_noncontact_requests_are_identical(self):
  raw=json.loads((ROOT/'experiments/artem-pr4-20261111/eval/cases_v3.json').read_text())
  cases=raw['cases'] if isinstance(raw,dict) else raw
  cfg=Settings('http://localhost/v1','test','test');client=Capture()
  svc=Consultant(client,LexicalRetriever.from_zip(ROOT/'data/knowledge-base.zip'),cfg)
  unchanged=[];routed=[]
  for c in cases:
   req=ConsultationRequest(c['id'],parse_question(c['question']))
   consultant.answer_prompt=answer_prompt
   svc.respond(req,answer_only=True);new=client.messages
   consultant.answer_prompt=lambda messages:ANSWER_PROMPT
   svc.respond(req,answer_only=True);old=client.messages
   self.assertEqual(new[1],old[1])
   if answer_prompt(req.messages)==ANSWER_PROMPT:
    self.assertEqual(new,old);unchanged.append(c['id'])
   else:routed.append(c['id'])
  consultant.answer_prompt=answer_prompt
  self.assertGreater(len(unchanged),100)
  (ROOT/'reports/private/a5-contact-prompt-20261111/payload-check.json').write_text(json.dumps({'unchanged_requests':unchanged,'contact_routed':routed,'same_context_all':True},indent=2))
if __name__=='__main__':unittest.main()
