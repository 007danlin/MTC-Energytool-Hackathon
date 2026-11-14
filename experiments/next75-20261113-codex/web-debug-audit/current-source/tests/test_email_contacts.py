"""Evidence, correction and optional contact channels in the structured web path."""
import unittest
from consultant import Consultant, contact_value, extract_lead, lead_is_ready, valid_email
from contracts import ConsultationRequest, LeadState, Message
from retrieval import FixedRetriever
from tests.test_core import CFG, FRAGMENT, ScriptedClient, payload


class EmailContactTests(unittest.TestCase):
    def test_bounded_ascii_mailbox_syntax(self):
        for value in ('User+case@Example.COM', 'x@a-b.example', "a!#$%&'*+-/=?^_`{|}~@example.com", 'a'*64+'@example.com'):
            with self.subTest(value=value): self.assertTrue(valid_email(value))
        for value in ('', 'x', 'x@localhost', 'x@@example.com', 'a..b@example.com', '.a@example.com', 'a.@example.com',
                      'Name <x@example.com>', 'x@example.com,y@example.com', 'x@y..com', 'x@-a.com', 'x@a-.com',
                      'a'*65+'@example.com', 'x@'+'a'*64+'.com', 'ю@example.com', 'x@пример.рф', 'x@a.com\n'):
            with self.subTest(value=value): self.assertFalse(valid_email(value))

    def test_email_only_lead_ready_without_requesting_phone(self):
        text = 'Свяжите со специалистом по почте User+site@Example.COM. Телефон не укажу.'
        data = payload(answer='Заявка сформирована.', contacts=[{'field':'email', 'value':'User+site@Example.COM', 'message_index':0, 'quote':text}],
                       intent={'requested':True, 'declined':False, 'message_index':0, 'quote':'Свяжите со специалистом'})
        service = Consultant(ScriptedClient(data), FixedRetriever([FRAGMENT]), CFG)
        result = service.respond(ConsultationRequest('s',[Message('user',text)]))
        self.assertTrue(result.lead_ready)
        self.assertEqual(result.lead.fields, {'email':'User+site@Example.COM'})
        self.assertEqual(result.summary['contacts'], result.lead.fields)
        self.assertEqual(result.summary['missing_fields'], [])
        self.assertEqual(result.summary['delivery_status'], 'prepared')
        self.assertFalse(result.summary['sent'])
        self.assertEqual(result.answer, 'Заявка сформирована.')

    def test_email_must_match_whole_user_mailbox(self):
        self.assertEqual(contact_value('email','a@example.com','Пишите a@example.com.'),'a@example.com')
        self.assertIsNone(contact_value('email','a@example.com','Пишите other-a@example.com'))
        for mixed in ('Жfoo@example.org', 'foo@example.orgЖ', 'foo@example.org.рф'):
            with self.subTest(mixed=mixed):
                self.assertIsNone(contact_value('email','foo@example.org','Мой адрес '+mixed))
        messages=[Message('assistant','Пишите fake@example.com'),Message('user','Мой адрес real@example.com')]
        lead=extract_lead(payload(contacts=[{'field':'email','value':'fake@example.com','message_index':0,'quote':messages[0].content},
                                          {'field':'email','value':'fake@example.com','message_index':1,'quote':messages[1].content}]), ConsultationRequest('s',messages))
        self.assertEqual(lead.fields,{})

    def test_truncated_quote_cannot_create_a_different_address(self):
        for actual, claimed in (('Жfoo@example.org','foo@example.org'), ('alice@example.org','ice@example.org'),
                                ('foo@example.orgЖ','foo@example.org')):
            with self.subTest(actual=actual):
                messages=[Message('user','Мой email '+actual)]
                evidence={'message_index':0,'quote':claimed}
                data=payload(contacts=[{'field':'email','value':claimed,**evidence}])
                self.assertEqual(extract_lead(data,ConsultationRequest('s',messages)).fields,{})
                old=LeadState('s',{'email':claimed},{'email':evidence})
                self.assertEqual(extract_lead(payload(),ConsultationRequest('s',messages,old)).fields,{})
        messages=[Message('user','Пишите Client.Name@Example.ORG')]
        data=payload(contacts=[{'field':'email','value':'client.name@example.org','message_index':0,'quote':'client.name@example.org'}])
        self.assertEqual(extract_lead(data,ConsultationRequest('s',messages)).fields,{'email':'Client.Name@Example.ORG'})

    def test_email_correction_withdrawal_and_no_resurrection(self):
        messages=[Message('user','Пишите old@example.com'), Message('user','Теперь пишите new@example.com')]
        old=LeadState('s',{'email':'new@example.com'}, {'email':{'message_index':1,'quote':messages[1].content}})
        stale=payload(contacts=[{'field':'email','value':'old@example.com','message_index':0,'quote':messages[0].content}])
        corrected=extract_lead(stale, ConsultationRequest('s',messages,old))
        self.assertEqual(corrected.fields['email'],'new@example.com')
        messages.append(Message('user','Удалите мою почту'))
        removed=extract_lead(payload(contacts=[{'field':'email','value':None,'message_index':2,'quote':messages[2].content}]), ConsultationRequest('s',messages,corrected))
        self.assertNotIn('email',removed.fields)
        self.assertNotIn('email',extract_lead(stale, ConsultationRequest('s',messages,removed)).fields)

    def test_old_phone_and_both_channels_retain_readiness(self):
        for fields in ({'phone':'+79990000001'}, {'email':'a@example.com'}, {'phone':'+79990000001','email':'a@example.com'}):
            self.assertTrue(lead_is_ready(LeadState('s',fields,requested=True)))
            self.assertFalse(lead_is_ready(LeadState('s',fields,requested=True,declined=True)))
