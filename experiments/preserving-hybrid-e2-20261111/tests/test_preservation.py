import hashlib,json,sys,tempfile,unittest
from array import array
from pathlib import Path
from contracts import Fragment
from hybrid_retrieval import HybridRetriever,ENCODING,MODEL,rows_signature
from test_index import Client,vector

def context(fs,cap):
 out=[];seen=set();used=0
 for f in fs:
  if f.source_id in seen or not f.text.strip() or used+len(f.text)>cap:continue
  out.append((f.source_id,f.text));seen.add(f.source_id);used+=len(f.text)
 return out
class Lex:
 def __init__(self,fragments,baseline):self.fragments=fragments;self.baseline=baseline
 def search(self,q,top_k):return self.baseline
class PreservationTests(unittest.TestCase):
 def make(self,fs,base,cap=32000):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);d=Path(temp.name)
  data=array('f',vector()*(len(fs)+2))
  if sys.byteorder!='little':data.byteswap()
  blob=data.tobytes();(d/'embedding_vectors.bin').write_bytes(blob)
  (d/'embedding_index.json').write_text(json.dumps({'schema':1,'model':MODEL,'encoding':ENCODING,'rows':rows_signature(fs),'probes':['a','b'],'vectors_sha256':hashlib.sha256(blob).hexdigest()}))
  return HybridRetriever(Lex(fs,base),d,Client(),context_chars=cap)
 def test_exact_prefix_order_text_and_score(self):
  fs=[Fragment('a.md','s001','New\nFact'),Fragment('z.md','s001','Baseline one\nBody',score=7.2),Fragment('y.md','s001','Baseline two\nBody',score=3.1)]
  base=fs[1:];r=self.make(fs,base);out=r.search('question')
  self.assertEqual(out[:len(base)],base)
  for before,after in zip(base,out):self.assertIs(before,after)
  self.assertEqual(context(out,32000)[:2],context(base,32000));self.assertIn(fs[0],out)
 def test_budget_keeps_original_context(self):
  fs=[Fragment('a.md','s001','a'*80),Fragment('z.md','s001','b'*120),Fragment('y.md','s001','c'*50)]
  for cap in [49,50,119,120,169,170,249,250]:
   base=fs[1:];out=self.make(fs,base,cap).search('question');expected=context(base,cap);actual=context(out,cap)
   self.assertEqual(actual[:len(expected)],expected);self.assertLessEqual(sum(len(t) for _,t in actual),cap)
 def test_whole_guard_bundle_or_no_addition(self):
  fs=[Fragment('a.md','s001','Claim\nFact'),Fragment('a.md','s002','Product > Чего утверждать нельзя\n'+'x'*100),Fragment('z.md','s001','Baseline\nBody')]
  base=[fs[-1]];cap=len(base[0].text)+len(fs[0].text)+5;out=self.make(fs,base,cap).search('question')
  self.assertEqual(out,base)
  out=self.make(fs,base).search('question');self.assertIn(fs[0],out);self.assertIn(fs[1],out)
 def test_baseline_guard_rejected_by_budget_blocks_new_claim(self):
  claim=Fragment('a.md','s001','Claim\nshort');guard=Fragment('a.md','s002','Product > Чего утверждать нельзя\n'+'x'*300);base=[Fragment('z.md','s001','base'*10),guard]
  r=self.make([claim]+base,base,100);self.assertEqual(r.search('q'),base)
 def test_at_most_four_novel_sections(self):
  fs=[Fragment('%02d.md'%i,'s001','Fact '+str(i)) for i in range(10)];base=[fs[-1]];out=self.make(fs,base).search('q')
  self.assertEqual(len(out)-len(base),4)
 def test_additional_character_cap(self):
  fs=[Fragment('%02d.md'%i,'s001','Text\n'+'x'*2000) for i in range(10)];base=[fs[-1]];out=self.make(fs,base).search('q')
  self.assertLessEqual(sum(len(f.text) for f in out[len(base):]),6000)
if __name__=='__main__':unittest.main()
