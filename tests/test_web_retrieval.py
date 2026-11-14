import json,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from web_retrieval import WebRetriever

class WebRetrievalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.kb=self.root/'kb.zip'
  with ZipFile(self.kb,'w') as z:
   z.writestr('20-products/22-askue.md','# Учёт\n\nПлатформа учета для склада.\n\n## Ограничения\n\nБез связи нужен отдельный анализ.')
   z.writestr('20-products/23-solar.md','# Солнце\n\nСолнечные панели для дневной работы.')
 def test_n2_documents_and_a2_are_selectable(self):
  n2=WebRetriever(self.kb,mode='n2',context_chars=8000)
  sources=n2.search('Учёт на складе')
  self.assertTrue(any('Без связи' in f.text for f in sources));self.assertEqual(n2.search(''),[])
  self.assertTrue(WebRetriever(self.kb,mode='a2').search('Склад'))
  with self.assertRaises(ValueError):WebRetriever(self.kb,mode='wrong')
 def test_snapshot_appears_and_revocation_reloads_without_restart(self):
  snapshot=self.root/'snapshot.json';r=WebRetriever(self.kb,snapshot_path=snapshot)
  self.assertFalse(any(f.document_id.startswith('90-expert/') for f in r.search('Zigbee')))
  d={'entry_id':'x','revision':1,'path':'90-expert/x-r1.md','source_id':'90-expert/x-r1.md#s001','markdown':'# Zigbee\n\nПроверенный ответ про Zigbee.'}
  snapshot.write_text(json.dumps({'kb_version':'v1','documents':[d]}))
  self.assertTrue(any(f.document_id.startswith('90-expert/') for f in r.search('Zigbee')));self.assertEqual(r.kb_version,'v1')
  snapshot.write_text(json.dumps({'kb_version':'v2','documents':[]}))
  self.assertFalse(any(f.document_id.startswith('90-expert/') for f in r.search('Zigbee')));self.assertEqual(r.kb_version,'v2')
  snapshot.write_text('{invalid')
  self.assertTrue(r.search('склад'));self.assertTrue(r.snapshot_error)
