import hashlib,json,sys,tempfile,unittest
from array import array
from pathlib import Path
from contracts import Fragment
from hybrid_retrieval import HybridRetriever,ENCODING,MODEL,rows_signature
from test_index import Client,vector
class Lex:
 def __init__(self,fs,base):self.fragments=fs;self.base=base
 def search(self,q,top_k):return self.base
class SelectionTests(unittest.TestCase):
 def make(self,base_ids,cap=32000,texts=None):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);d=Path(temp.name)
  fs=[Fragment('%02d.md'%i,'s001',texts[i] if texts else 'Evidence '+str(i)) for i in range(6)];base=[fs[i] for i in base_ids]
  a=array('f',vector()*8)
  if sys.byteorder!='little':a.byteswap()
  blob=a.tobytes();(d/'embedding_vectors.bin').write_bytes(blob)
  (d/'embedding_index.json').write_text(json.dumps({'schema':1,'model':MODEL,'encoding':ENCODING,'rows':rows_signature(fs),'probes':['a','b'],'vectors_sha256':hashlib.sha256(blob).hexdigest()}))
  return HybridRetriever(Lex(fs,base),d,Client(),context_chars=cap),base
 def test_no_missing_top3_exact_baseline(self):
  r,b=self.make([0,1,2,5]);self.assertEqual(r.search('q'),b)
 def test_one_missing_top3_exact_baseline(self):
  r,b=self.make([0,1,5]);self.assertEqual(r.search('q'),b)
 def test_two_missing_top3_expands_without_reordering(self):
  r,b=self.make([0,5]);out=r.search('q');self.assertEqual(out[:len(b)],b);self.assertGreater(len(out),len(b))
 def test_three_missing_top3_expands(self):
  r,b=self.make([4,5]);self.assertGreater(len(r.search('q')),len(b))
 def test_only_actual_accepted_baseline_counts(self):
  r,b=self.make([0,1,5],cap=80,texts=['x'*100,'one','two','three','four','five']);out=r.search('q')
  self.assertEqual(out[:len(b)],b);self.assertGreater(len(out),len(b));self.assertLessEqual(sum(len(f.text) for f in out if len(f.text)<=80),80)
if __name__=='__main__':unittest.main()
