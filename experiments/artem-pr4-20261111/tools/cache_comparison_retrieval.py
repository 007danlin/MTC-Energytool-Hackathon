"""Materialize exact retriever results before loading Qwen; never included in ZIP."""
import dataclasses
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from compare_retrievers import make_variants
from dialogue import parse_question, retrieval_query
from retrieval import load_fragments
from settings import Settings
settings=Settings.from_env()
cases=json.loads((ROOT/'eval/cases_v3.json').read_text())['cases']
cases=[c for c in cases if c['split']=='dev']
kb=ROOT/'data/knowledge-base.zip'
variants=make_variants(['A','B'],load_fragments(kb),settings,True)
cache={}
for name,retriever in variants.items():
    rows={}
    for case in cases:
        q=retrieval_query(parse_question(case['question']))
        rows[q]=[dataclasses.asdict(f) for f in retriever.search(q,settings.top_k)]
        print(name,case['id'],len(rows[q]),flush=True)
    cache[name]={'rows':rows,'stats':getattr(retriever,'stats',None)}
assert cache['B']['stats']['fallback_searches']==0
out=ROOT/'reports/private/retrieval-cache.json'
out.write_text(json.dumps({'top_k':settings.top_k,'kb_sha256':hashlib.sha256(kb.read_bytes()).hexdigest(),'cache':cache},ensure_ascii=False))
print(out,flush=True)
