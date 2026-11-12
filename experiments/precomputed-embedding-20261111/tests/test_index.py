import hashlib,json,sys,tempfile,time,unittest
from array import array
from pathlib import Path
from unittest.mock import patch
from contracts import Fragment
from retrieval import LexicalRetriever
from hybrid_retrieval import HybridRetriever,EmbeddingAPI,ENCODING,MODEL,rows_signature,unit
from settings import Settings

def vector(i=0):return [1. if j==i else 0. for j in range(1024)]
class Client:
 def __init__(self,wrong=False,error=False):self.calls=0;self.wrong=wrong;self.error=error
 def encode(self,texts,timeout=5):
  self.calls+=1
  if self.error:raise TimeoutError()
  return [vector(1 if self.wrong else 0) for _ in texts]
class IndexTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.d=Path(self.temp.name)
  self.lex=LexicalRetriever([Fragment('a.md','s1','Учёт\nПоказания приборов.'),Fragment('b.md','s1','Фото\nФотографии счётчиков.')])
  data=array('f',vector()*4)
  if sys.byteorder!='little':data.byteswap()
  blob=data.tobytes();(self.d/'embedding_vectors.bin').write_bytes(blob)
  self.meta={'schema':1,'model':MODEL,'encoding':ENCODING,'rows':rows_signature(self.lex.fragments),'probes':['контроль1','control2'],'vectors_sha256':hashlib.sha256(blob).hexdigest()}
  self.save()
 def tearDown(self):self.temp.cleanup()
 def save(self):(self.d/'embedding_index.json').write_text(json.dumps(self.meta))
 def assert_fallback(self,r):self.assertEqual(r.search('Показания приборов'),self.lex.search('Показания приборов'))
 def test_real_load_probe_and_cache(self):
  c=Client();r=HybridRetriever(self.lex,self.d,c);self.assertEqual(r.status['mode'],'pending')
  r.search('Показания приборов');r.search('Показания приборов');self.assertEqual(c.calls,2);self.assertEqual(r.status['mode'],'hybrid')
 def test_missing_index(self):
  (self.d/'embedding_index.json').unlink();c=Client();self.assert_fallback(HybridRetriever(self.lex,self.d,c));self.assertEqual(c.calls,0)
 def test_changed_corpus(self):
  self.meta['rows'][0][1]='changed';self.save();c=Client();self.assert_fallback(HybridRetriever(self.lex,self.d,c));self.assertEqual(c.calls,0)
 def test_other_model(self):
  c=Client();self.assert_fallback(HybridRetriever(self.lex,self.d,c,model='other'));self.assertEqual(c.calls,0)
 def test_wrong_pooling(self):
  self.meta['encoding']=dict(ENCODING,pooling='mean');self.save();self.assert_fallback(HybridRetriever(self.lex,self.d,Client()))
 def test_corrupt_bytes(self):
  p=self.d/'embedding_vectors.bin';data=bytearray(p.read_bytes());data[0]^=1;p.write_bytes(data);self.assert_fallback(HybridRetriever(self.lex,self.d,Client()))
 def test_truncated_file(self):
  p=self.d/'embedding_vectors.bin';p.write_bytes(p.read_bytes()[:-4]);self.assert_fallback(HybridRetriever(self.lex,self.d,Client()))
 def test_wrong_space_disables(self):
  c=Client(wrong=True);r=HybridRetriever(self.lex,self.d,c);self.assert_fallback(r);self.assert_fallback(r);self.assertEqual(c.calls,1);self.assertFalse(r.enabled)
 def test_timeout_disables(self):
  c=Client(error=True);r=HybridRetriever(self.lex,self.d,c);self.assert_fallback(r);self.assert_fallback(r);self.assertEqual(c.calls,1)
 def test_long_query_preserves_lexical(self):
  c=Client();r=HybridRetriever(self.lex,self.d,c);q='Показания '*600;self.assertEqual(r.search(q),self.lex.search(q));self.assertEqual(c.calls,0);self.assertTrue(r.enabled)
 def test_empty_top_k(self):
  c=Client();self.assertEqual(HybridRetriever(self.lex,self.d,c).search('test',0),[]);self.assertEqual(c.calls,0)
 def test_unit_validation(self):
  for v in [[],[0.]*1024,[float('nan')]*1024,[float('inf')]*1024,[True]*1024]:
   with self.subTest():
    with self.assertRaises(ValueError):unit(v)
  self.assertEqual(unit([2.]+[0.]*1023),vector())
class APItests(unittest.TestCase):
 def setUp(self):self.cfg=Settings('http://localhost/v1','test','generation-model')
 def response(self,payload):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return json.dumps(payload).encode()
  return Response()
 def test_order_and_auth_contract(self):
  body={'model':MODEL,'data':[{'index':1,'embedding':vector(1)},{'index':0,'embedding':vector()}]}
  with patch('urllib.request.urlopen',return_value=self.response(body)) as call:
   result=EmbeddingAPI(self.cfg,MODEL).encode(['a','b']);self.assertEqual(result,[vector(),vector(1)])
   req=call.call_args.args[0];self.assertEqual(req.full_url,'http://localhost/v1/embeddings');self.assertEqual(req.headers['Authorization'],'Bearer test')
   self.assertEqual(json.loads(req.data)['model'],MODEL)
 def test_bad_response_rejected(self):
  for body in [{'data':[]},{'model':'other','data':[{'index':0,'embedding':vector()}]},{'data':[{'index':4,'embedding':vector()}]},{'data':[{'index':0,'embedding':[1,2]}]}]:
   with patch('urllib.request.urlopen',return_value=self.response(body)):
    with self.assertRaises(ValueError):EmbeddingAPI(self.cfg,MODEL).encode(['a'])
 def test_deadline_before_network(self):
  with patch('urllib.request.urlopen') as call:
   with self.assertRaises(ValueError):EmbeddingAPI(self.cfg,MODEL,time.monotonic()+10).encode(['a'])
   self.assertFalse(call.called)
if __name__=='__main__':unittest.main()
