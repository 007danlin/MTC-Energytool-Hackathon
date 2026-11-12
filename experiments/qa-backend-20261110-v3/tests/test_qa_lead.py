import tempfile
import unittest
from contracts import ConsultationRequest, Message, LeadState
from consultant import Consultant, lead_is_ready
from integration import save_prepared_lead
from test_core import ScriptedClient, FixedRetriever, FRAGMENT, CFG, payload

class QALeadTests(unittest.TestCase):
    def respond(self, text, **changes):
        model = payload(status='lead_step', citations=[], **changes)
        service = Consultant(ScriptedClient(model), FixedRetriever([FRAGMENT]), CFG)
        return service.respond(ConsultationRequest('qa', [Message('user', text)]))

    def prepared(self):
        text='Подготовьте заявку. Нужен учёт трёх площадок. Телефон +79990000001.'
        return self.respond(text, answer='Сэкономите 90%, менеджер завтра позвонит.',
            contacts=[dict(field='phone',value='+79990000001',message_index=0,quote=text)],
            intent=dict(requested=True,declined=False,message_index=0,quote='Подготовьте заявку.'),
            summary={'task':[dict(value='выдуманный продукт',message_index=0,quote='Нужен учёт трёх площадок.')]})

    def test_phone_only_is_ready_and_no_unverified_model_claims(self):
        r=self.prepared()
        self.assertTrue(r.lead_ready); self.assertEqual(r.summary['missing_fields'],[])
        self.assertEqual(set(r.summary['optional_missing_fields']),{'full_name','company'})
        self.assertIn('+79990000001',r.answer);self.assertIn('трёх площадок',r.answer)
        self.assertNotIn('90%',r.answer);self.assertNotIn('позвонит',r.answer)
        self.assertNotIn('выдуманный',r.summary['brief']);self.assertEqual(r.sources,[])
        self.assertEqual(r.debug['repairs'],0);self.assertFalse(r.summary['sent'])

    def test_request_without_contact_asks_only_phone(self):
        text='Хочу связаться с менеджером'
        r=self.respond(text,intent=dict(requested=True,declined=False,message_index=0,quote=text))
        self.assertFalse(r.lead_ready);self.assertEqual(r.summary['missing_fields'],['phone'])
        self.assertIn('телефон',r.answer.lower());self.assertNotIn('мощност',r.answer)

    def test_company_is_not_contact(self):
        self.assertFalse(lead_is_ready(LeadState('qa',{'company':'Завод'},requested=True)))

    def test_contact_without_consent_not_ready(self):
        self.assertFalse(lead_is_ready(LeadState('qa',{'phone':'+79990000001'})))

    def test_refusal_does_not_ask_contact(self):
        text='Не хочу оставлять телефон'
        r=self.respond(text,intent=dict(requested=False,declined=True,message_index=0,quote=text))
        self.assertFalse(r.lead_ready);self.assertNotIn('Какой телефон',r.answer)

    def test_fabricated_phone_does_not_prepare(self):
        text='Нужен менеджер'
        r=self.respond(text,contacts=[dict(field='phone',value='+79990000001',message_index=0,quote=text)],
                       intent=dict(requested=True,declined=False,message_index=0,quote=text))
        self.assertFalse(r.lead_ready);self.assertNotIn('+79990000001',r.answer)

    def test_product_answer_still_requires_citation(self):
        service=Consultant(ScriptedClient(payload(citations=[])),FixedRetriever([FRAGMENT]),CFG)
        r=service.respond(ConsultationRequest('qa',[Message('user','Что делает платформа?')]))
        self.assertEqual(r.status,'technical_error');self.assertEqual(r.debug['error_code'],'missing_evidence')

    def test_local_export_retains_contact_and_actual_task(self):
        r=self.prepared()
        with tempfile.TemporaryDirectory() as directory:
            path=save_prepared_lead(r,directory);text=path.read_text()
            self.assertIn('+79990000001',text);self.assertIn('трёх площадок',text)
            self.assertIn('Внешней отправки не было',text);self.assertEqual(path.stat().st_mode & 0o777,0o600)
            r.lead.declined=True
            with self.assertRaises(ValueError):save_prepared_lead(r,directory)

    def test_unused_bad_citation_cannot_break_rendered_contact_step(self):
        text='Подготовьте заявку. Телефон +79990000001.'
        model=payload(status='lead_step',answer='Скидка 90%, менеджер позвонит завтра.',
            citations=[dict(source_id='invented',quote='Это выдуманная цитата')],
            contacts=[dict(field='phone',value='+79990000001',message_index=0,quote=text)],
            intent=dict(requested=True,declined=False,message_index=0,quote='Подготовьте заявку.'))
        service=Consultant(ScriptedClient(model),FixedRetriever([FRAGMENT]),CFG)
        r=service.respond(ConsultationRequest('qa',[Message('user',text)]))
        self.assertTrue(r.lead_ready);self.assertEqual(r.debug['repairs'],0)
        self.assertEqual(r.sources,[]);self.assertNotIn('Скидка',r.answer);self.assertNotIn('позвонит',r.answer)

    def test_bad_product_prose_is_not_exposed_when_preparing_valid_contact(self):
        text='Подготовьте заявку. Телефон +79990000001.'
        model=payload(answer='Гарантирована скидка 90% и звонок завтра.',citations=[],
            contacts=[dict(field='phone',value='+79990000001',message_index=0,quote=text)],
            intent=dict(requested=True,declined=False,message_index=0,quote='Подготовьте заявку.'))
        service=Consultant(ScriptedClient(model),FixedRetriever([FRAGMENT]),CFG)
        r=service.respond(ConsultationRequest('qa',[Message('user',text)]))
        self.assertEqual(r.status,'lead_step');self.assertTrue(r.lead_ready)
        self.assertTrue(r.debug['product_answer_rejected']);self.assertEqual(r.debug['error_code'],'missing_evidence')
        self.assertNotIn('90%',r.answer);self.assertNotIn('завтра',r.answer)
        self.assertIn('не удалось подтвердить',r.answer);self.assertFalse(r.summary['sent'])

    def test_bad_citation_without_confirmed_intent_cannot_create_contact_fallback(self):
        text='Телефон +79990000001. Что делает платформа?'
        model=payload(citations=[],contacts=[dict(field='phone',value='+79990000001',message_index=0,quote=text)])
        service=Consultant(ScriptedClient(model),FixedRetriever([FRAGMENT]),CFG)
        r=service.respond(ConsultationRequest('qa',[Message('user',text)]))
        self.assertEqual(r.status,'technical_error');self.assertFalse(r.lead_ready)
