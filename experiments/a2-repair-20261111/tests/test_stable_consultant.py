import json
import unittest
from consultant import Consultant
from stable_consultant import StableConsultant
from contracts import ConsultationRequest, Message, Fragment
from retrieval import FixedRetriever
from settings import Settings

class Client:
    def __init__(self):self.calls=[]
    def complete(self,messages,**kw):self.calls.append((messages,kw));return 'Нужна проверка конкретных условий.'

class StableTests(unittest.TestCase):
    def setup_services(self):
        cfg=Settings('http://localhost/v1','test','test')
        retriever=FixedRetriever([Fragment('p.md','s001','Продукт > Условия\nНужна проверка конкретных условий.')])
        a,b=Client(),Client()
        return Consultant(a,retriever,cfg),StableConsultant(b,retriever,cfg),a,b
    def test_product_question_uses_exact_base_generation_request_once(self):
        a,b,ca,cb=self.setup_services();r=ConsultationRequest('x',[Message('user','Каковы условия работы системы?')])
        x=a.respond(r,deadline=1000,answer_only=True);y=b.respond(r,deadline=1000,answer_only=True)
        self.assertEqual(ca.calls,cb.calls);self.assertEqual(len(cb.calls),1);self.assertEqual(x.answer,y.answer)
        self.assertEqual(y.debug['evidence_validation'],'format_only_unverified_generation')
    def test_clear_contact_creates_draft_without_generation_or_delivery(self):
        _,s,_,c=self.setup_services();r=ConsultationRequest('x',[Message('user','Нужен менеджер по учёту воды, телефон +7 912 123-45-67.')])
        out=s.respond(r,answer_only=True)
        self.assertEqual(c.calls,[]);self.assertIn('+79121234567',out.answer);self.assertIn('ничего не отправлено',out.answer);self.assertFalse(out.debug['external_delivery'])
    def test_contact_with_substantive_question_still_gets_base_answer(self):
        _,s,_,c=self.setup_services();r=ConsultationRequest('x',[Message('user','Позвоните на +7 912 123-45-67. Поддерживается ли вода?')])
        out=s.respond(r,answer_only=True)
        self.assertEqual(len(c.calls),1);self.assertEqual(out.debug['mode'],'a2_repaired')
if __name__=='__main__':unittest.main()
