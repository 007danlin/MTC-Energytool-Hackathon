import json
import unittest
import time
from contracts import Fragment,Message,ConsultationRequest
from settings import Settings
from evidence_pipeline import EvidenceConsultant,section_index
class Retriever:
 def __init__(self):self.fragments=(Fragment('product.md','s001','Продукт > Ограничение\nЗапуск возможен после проверки условий проекта.'),)
 def search(self,*args):return list(self.fragments)
class Client:
 def __init__(self,answers):self.answers=list(answers);self.calls=0;self.deadlines=[]
 def complete(self,*a,**kw):self.calls+=1;self.deadlines.append(kw.get('deadline'));return self.answers.pop(0)
class PipelineTests(unittest.TestCase):
 def service(self,answers):
  c=Client(answers);return EvidenceConsultant(c,Retriever(),Settings('http://localhost/v1','test','test')),c
 def request(self):return ConsultationRequest('case',[Message('user','Можно ли запустить проект?')])
 def plan(self,selected=None):return json.dumps({'task':'Запуск','query':'Когда можно запускать?','selected':[0] if selected is None else selected})
 def review(self,**kw):
  r={'supported':True,'remove_sentences':[],'issues':[],'evidence':[{'index':0,'quote':'Запуск возможен после проверки условий проекта.'}]};r.update(kw);return json.dumps(r,ensure_ascii=False)
 def test_selected_and_reviewed_correct_answer(self):
  s,c=self.service([self.plan(),'Запуск возможен после проверки условий проекта.',self.review()]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(c.calls,3);self.assertEqual(r.debug['planner'],'selected');self.assertEqual(r.debug['review'],'accepted');self.assertEqual(r.debug['evidence_validation'],'model_review_with_resolved_sources')
 def test_verifier_correction_replaces_draft(self):
  s,c=self.service([self.plan(),'Да, гарантированно.',self.review(supported=False,remove_sentences=[0],evidence=[{'index':0,'quote':'Запуск возможен после проверки условий проекта.','add':True}],issues=['unsupported_guarantee'])]);r=s.respond(self.request(),answer_only=True)
  self.assertIn('Запуск возможен после проверки условий проекта.',r.answer);self.assertNotIn('гарантированно',r.answer);self.assertEqual(r.debug['review'],'corrected')
 def test_fabricated_quote_cannot_be_reported_verified(self):
  s,c=self.service([self.plan(),'Нужна проверка.',self.review(evidence=[{'index':0,'quote':'Любой проект гарантированно запускается.'}])]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['review'],'failed');self.assertEqual(r.debug['evidence_validation'],'unverified_draft_fallback');self.assertEqual(r.answer,'Нужна проверка.')
 def test_empty_selection_valid_not_hidden_baseline(self):
  s,c=self.service([self.plan([]),'В базе не подтверждены условия.',self.review(evidence=[])]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['planner'],'empty');self.assertEqual(r.debug['retrieved_sources'],[]);self.assertEqual(c.calls,3)
 def test_invalid_plan_explicit_baseline_fallback(self):
  s,c=self.service([self.plan([999]),'Нужна проверка проекта.']);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['planner'],'fallback');self.assertEqual(r.debug['evidence_validation'],'unverified_a2_fallback');self.assertEqual(c.calls,2)
 def test_empty_evidence_cannot_certify_factual_context(self):
  s,c=self.service([self.plan(),'Нужна проверка.',self.review(evidence=[])]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['review'],'failed');self.assertEqual(r.debug['review_error'],'review_missing_evidence')
 def test_free_form_reviewer_answer_is_not_used(self):
  review=self.review(supported=False,remove_sentences=[0],corrected_answer='Гарантируется запуск за10дней.',evidence=[{'index':0,'quote':'Запуск возможен после проверки условий проекта.','add':True}])
  s,c=self.service([self.plan(),'Да, гарантированно.',review]);r=s.respond(self.request(),answer_only=True)
  self.assertNotIn('10',r.answer);self.assertNotIn('гарантированно',r.answer);self.assertIn('после проверки',r.answer)
 def test_planner_reserves_time_for_answer(self):
  s,c=self.service([self.plan(),'Нужна проверка.',self.review()]);end=time.monotonic()+60
  s.respond(self.request(),deadline=end,answer_only=True)
  self.assertLess(c.deadlines[0],end-20);self.assertEqual(c.deadlines[1],end);self.assertEqual(c.deadlines[2],end)
 def test_oversized_correction_preserves_original_draft(self):
  draft='А'*9995
  s,c=self.service([self.plan(),draft,self.review(supported=False,evidence=[{'index':0,'quote':'Запуск возможен после проверки условий проекта.','add':True}])]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.answer,draft);self.assertEqual(r.debug['review'],'failed');self.assertEqual(r.debug['review_error'],'review_answer_length')
 def test_added_quote_preserves_source_negation_and_context(self):
  source='Продукт > Ограничения\nМы не гарантируем снижение расходов на40процентов.'
  r=Retriever();r.fragments=(Fragment('product.md','s001',source),)
  review={'supported':False,'remove_sentences':[0],'evidence':[{'index':0,'quote':'гарантируем снижение расходов на40процентов.','add':True}]}
  c=Client([self.plan(),'Гарантируем снижение.',json.dumps(review)]);s=EvidenceConsultant(c,r,Settings('http://localhost/v1','test','test'))
  out=s.respond(self.request(),answer_only=True)
  self.assertIn('Мы не гарантируем',out.answer);self.assertIn('Продукт > Ограничения',out.answer);self.assertNotIn('Гарантируем снижение.',out.answer)
 def test_scalar_planner_fields_are_used(self):
  plan=json.dumps({'task':'Запуск','query':'Условия запуска','section_1':0,'section_2':None,'section_3':None,'section_4':None})
  s,c=self.service([plan,'Нужна проверка.',self.review()]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['planner'],'selected');self.assertEqual(c.calls,3)
 def test_overbroad_valid_plan_is_ranked_without_baseline_fallback(self):
  r=Retriever();r.fragments=tuple(Fragment('product.md','s%03d'%i,('Продукт > Раздел'+str(i)+'\n'+('Запуск возможен после проверки условий проекта.' if i==7 else 'Описание компонента системы.'))) for i in range(12))
  review={'supported':True,'evidence':[{'index':7,'quote':'Запуск возможен после проверки условий проекта.'}]}
  c=Client([self.plan(list(range(12))),'Нужна проверка.',json.dumps(review)]);s=EvidenceConsultant(c,r,Settings('http://localhost/v1','test','test'))
  out=s.respond(self.request(),answer_only=True)
  self.assertEqual(out.debug['planner'],'selected');self.assertTrue(out.debug['selection_reduced']);self.assertIn(7,out.debug['planned_indices']);self.assertLessEqual(len(out.debug['planned_indices']),8);self.assertEqual(c.calls,3)
 def test_explicit_index_prefix_is_accepted_in_plan_and_evidence(self):
  plan=json.dumps({'task':'Запуск','query':'Условия запуска','section_1':'i:0','section_2':None,'section_3':None,'section_4':None})
  review=self.review(evidence=[{'index':'index:0','quote':'Запуск возможен после проверки условий проекта.'}])
  s,c=self.service([plan,'Нужна проверка.',review]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['planner'],'selected');self.assertEqual(r.debug['review'],'accepted');self.assertEqual(c.calls,3)
 def test_malformed_indices_not_silently_coerced(self):
  for bad in (True,1.0,None,'0-3','i:1 and2','документ0','-1'):
   with self.subTest(value=bad):
    with self.assertRaises(ValueError):section_index(bad)
 def test_reviewer_resolves_source_without_regenerating_quote(self):
  s,c=self.service([self.plan(),'Нужна проверка.',self.review(evidence=[{'index':0,'add':False}])]);r=s.respond(self.request(),answer_only=True)
  self.assertEqual(r.debug['review'],'accepted');self.assertEqual(r.debug['review_sources'],[0])
 def test_rare_anchor_never_introduces_unselected_document(self):
  r=Retriever();r.fragments+=(Fragment('other.md','s001','Иной продукт\nСахалин допускает иные условия.'),)
  c=Client([self.plan(),'Нужна проверка.',self.review()]);s=EvidenceConsultant(c,r,Settings('http://localhost/v1','test','test'))
  out=s.respond(ConsultationRequest('x',[Message('user','Каковы условия запуска на Сахалине?')]),answer_only=True)
  self.assertNotIn(1,out.debug['planned_indices']);self.assertNotIn(1,out.debug['anchor_indices'])
 def test_review_must_not_turn_short_answer_into_long_source_dump(self):
  r=Retriever();r.fragments=(Fragment('product.md','s001','Продукт > Описание\n'+'Сведения о возможностях. '*70),)
  review={'supported':False,'remove_sentences':[0],'evidence':[{'index':0,'add':True}]}
  c=Client([self.plan(),'Нужна проверка проекта.',json.dumps(review)]);s=EvidenceConsultant(c,r,Settings('http://localhost/v1','test','test'))
  out=s.respond(self.request(),answer_only=True)
  self.assertEqual(out.answer,'Нужна проверка проекта.');self.assertEqual(out.debug['review'],'failed');self.assertEqual(out.debug['review_error'],'review_answer_too_verbose')
 def test_small_soft_share_skips_extra_stages_but_keeps_global_deadline(self):
  s,c=self.service(['Нужна проверка проекта.']);end=time.monotonic()+300
  out=s.respond(self.request(),deadline=end,answer_only=True,budget_hint=20)
  self.assertEqual(c.calls,1);self.assertEqual(c.deadlines,[end]);self.assertEqual(out.debug['planner'],'budget_skip');self.assertEqual(out.answer,'Нужна проверка проекта.')
if __name__=='__main__':unittest.main()
