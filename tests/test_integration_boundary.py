import unittest
from consultant import Consultant,unconfirmed_integration_target
from contracts import ConsultationRequest,Message,Fragment
from retrieval import FixedRetriever
from settings import Settings

class IntegrationBoundaryTests(unittest.TestCase):
 def test_generic_protocols_do_not_prove_unknown_named_integration(self):
  source=Fragment('base.md','s1','Платформа поддерживает обмен данными по HTTP и MQTT.')
  class NoModel:
   def complete(self,*a,**k):raise AssertionError('No evidence for this named target')
  request=ConsultationRequest('guard',[Message('user','Можно ли интегрировать платформу с системой Warehouse-X7?')])
  result=Consultant(NoModel(),FixedRetriever([source]),Settings('http://unused','fixture','fixture')).respond(request)
  self.assertEqual(result.status,'knowledge_gap');self.assertIn('нет подтверждения',result.answer)
  self.assertIn('не означает',result.answer);self.assertNotIn('не поддерживается',result.answer)
  self.assertEqual(result.debug['routing'],'unconfirmed_named_integration')
 def test_known_target_and_generic_system_still_use_normal_consultation(self):
  source=Fragment('base.md','s1','Описана интеграция с системой Warehouse-X7 при указанных условиях.')
  self.assertIsNone(unconfirmed_integration_target('Можно ли интегрировать с системой Warehouse-X7?', [source]))
  self.assertIsNone(unconfirmed_integration_target('Как интегрировать с системой учёта?', []))
  self.assertEqual(unconfirmed_integration_target('Есть интеграция с системой «Склад Альфа»?',[]),'Склад Альфа')
