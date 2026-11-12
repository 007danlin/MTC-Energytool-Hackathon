"""Create review pairs as B completes, without exposing variant labels to reviewer."""
import json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
out=ROOT.parents[1]/'reports/private/artem-pr4-qwen-cached-20261111'
cases=json.loads((ROOT/'eval/cases_v3.json').read_text())['cases']
cases=[c for c in cases if c['split']=='dev']
a=json.loads((out/'checkpoint-A.json').read_text())
b=json.loads((out/'checkpoint-B.json').read_text()) if (out/'checkpoint-B.json').exists() else {}
rng=random.Random(849217)
pairs=[];key={}
for c in cases:
    names=['A','B'];rng.shuffle(names);pid=c['id']
    key[pid]=dict(zip(['left','right'],names))
    if pid not in a or pid not in b: continue
    rows={'A':a[pid],'B':b[pid]}
    pairs.append({'id':pid,'question':c['question'],
        'required':[{'fact':f['fact'],'evidence':list(dict.fromkeys(s['quote'] for s in f['sources']))} for f in c['required_facts']],
        'conditional':[{'condition':f['condition'],'fact':f['fact'],'evidence':list(dict.fromkeys(s['quote'] for s in f['sources']))} for f in c['conditional_facts']],
        'forbidden':[f['claim'] for f in c['forbidden_claims']],
        'acceptable_unknowns':c['acceptable_unknowns'],
        'left':rows[names[0]]['answer'],'right':rows[names[1]]['answer']})
(out/'review-pairs.json').write_text(json.dumps(pairs,ensure_ascii=False,indent=1))
(out/'review-key.json').write_text(json.dumps(key,indent=1))
print('Complete blinded pairs:',len(pairs))
