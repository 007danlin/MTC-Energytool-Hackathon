from pathlib import Path
from collections import Counter
import sys,json,hashlib,importlib.util
D=Path(__file__).resolve().parents[1];R=D.parent;H=R/'handoff'
sys.dont_write_bytecode=True
sys.path.insert(0,str(H/'winner/source'))
from consultant import Consultant
from settings import Settings
from dialogue import retrieval_query
from dialogue_n1 import parse_dialogue
spec=importlib.util.spec_from_file_location('n7_final_retrieval',D/'final-source/retrieval.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
settings=Settings.from_env({'LLM_BASE_URL':'http://unused.invalid/v1','LLM_API_KEY':'unused','LLM_MODEL':'unused'})
kb=H/'sources/organizers/drive-download-20261109T164943Z-1-001/knowledge-base.zip'
base=Consultant(None,kb,settings);cand=Consultant(None,kb,settings);cand.wide=mod.WideRetriever(cand.fragments)
traces={'N2':[],'N7':[]}
for name,obj in [('N2',base),('N7',cand)]:
 original=obj.wide.search_documents
 def traced(*args,_name=name,_original=original,**kwargs):
  fs=_original(*args,**kwargs)
  traces[_name].append({'budget':args[3] if len(args)>3 else kwargs.get('budget_chars',60000),'items':[(f.source_id,f.text) for f in fs]})
  return fs
 obj.wide.search_documents=traced
cases=json.loads((D/'panel.json').read_text())['cases']+json.loads((R/'new-panel-v1.json').read_text())['cases']
rows=[]
for case in cases:
 m=parse_dialogue(case['question']);q=retrieval_query(m)
 for limit in [90000,75000,65000,55000]:
  traces['N2'].clear();traces['N7'].clear();base.state.allowed=cand.state.allowed=limit
  a=base._build(m,q,'docs');b=cand._build(m,q,'docs')
  assert (a is None)==(b is None),(case['id'],limit,'mode availability differs')
  assert len(traces['N2'])==len(traces['N7']),(case['id'],limit,'shrink iterations differ')
  for ta,tb in zip(traces['N2'],traces['N7']):
   assert ta['budget']==tb['budget']
   assert Counter(ta['items'])==Counter(tb['items']),(case['id'],limit,'source drift')
  if a is not None:
   assert a[1]==b[1] and a[0][0]==b[0][0]
   assert sum(len(x['content']) for x in a[0])==sum(len(x['content']) for x in b[0])
  rows.append({'id':case['id'],'allowed_chars':limit,'docs_fit':a is not None,'shrink_iterations':len(traces['N2']),'same_iteration_budgets':True,'all_iteration_source_multisets_equal':True,'prompt_characters_equal':a is None or sum(len(x['content']) for x in a[0])==sum(len(x['content']) for x in b[0])})
result={'kind':'static context-shrink source preservation on exact extracted ZIP code; not model quality','candidate_retrieval_sha256':hashlib.sha256((D/'final-source/retrieval.py').read_bytes()).hexdigest(),'checks':len(rows),'passed':len(rows),'docs_unavailable_in_both':sum(not x['docs_fit'] for x in rows),'multiple_shrink_iterations':sum(x['shrink_iterations']>1 for x in rows),'rows':rows}
(D/'technical/final-shrink-preservation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
