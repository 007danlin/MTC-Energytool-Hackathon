import json,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'tools/prepare_incremental_blind.py'))
out=ROOT.parents[1]/'reports/private/artem-pr4-qwen-cached-20261111'
done={r['id'] for r in json.loads((out/'blind-review.json').read_text())}
for r in json.loads((out/'review-pairs.json').read_text()):
 if r['id'] in done:continue
 for k in ['required','conditional']:
  for f in r[k]:f.pop('evidence',None)
 print(json.dumps(r,ensure_ascii=False))
