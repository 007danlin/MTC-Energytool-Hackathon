import unittest
from hybrid_retrieval import contact_turn
import test_selection
class ContactTests(unittest.TestCase):
 def test_phone_with_contact_intent(self):
  for text in ['Да, звоните на +7 900 234-56-78.','Телефон 89001234567, подготовьте заявку.']:
   self.assertTrue(contact_turn(text+'\n'+text+'\nКонтекст разговора:\nАрхив фотографий'))
 def test_email_handoff(self):self.assertTrue(contact_turn('Почта для менеджера user@example.org'))
 def test_old_contact_does_not_block_new_question(self):
  self.assertFalse(contact_turn('Как работает станция?\nКак работает станция?\nКонтекст разговора:\nМой телефон +7 900 123-45-67'))
 def test_product_numbers_not_contacts(self):
  for q in ['Какая точность? Более90% или95%?','Станция750кВт, до20МВт','Телефон не дам, сравните счета','Поверка26.09.2026','Номер прибора89001234567. Какие настройки?']:
   self.assertFalse(contact_turn(q))
 def test_handoff_returns_exact_a2_without_embedding(self):
  fixture=test_selection.SelectionTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  r,base=fixture.make([0,5]);self.assertEqual(r.search('Звоните +7 900 234-56-78'),base);self.assertEqual(r.client.calls,0)
if __name__=='__main__':unittest.main()
