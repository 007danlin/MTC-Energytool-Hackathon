"""Build a minimal, isolated source-order experiment from exact N2 bytes."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
EXP = ROOT.parent
WINNER = EXP / 'handoff/winner/mts-energytool-n2-docs.zip'
EXPECTED = 'a22d786f895257e14fb89e747a674cd419be0d711ed43b834fb9442ef3b6ac9b'
assert hashlib.sha256(WINNER.read_bytes()).hexdigest() == EXPECTED
OUT = ROOT / 'candidate'
OUT.mkdir(exist_ok=False)
with zipfile.ZipFile(WINNER) as z:
    for item in z.infolist():
        assert '/' not in item.filename and '\\' not in item.filename
        (OUT / item.filename).write_bytes(z.read(item))
p = OUT / 'retrieval.py'
before = p.read_text()
old = '        return self.ordered([self.fragments[i] for i in chosen])\n'
new = '''        ordered = self.ordered([self.fragments[i] for i in chosen])
        # Relative references depend on source order. Keep their complete
        # preceding/following selected span fixed instead of moving a fragment
        # across the passage to which "see above/below" may refer.
        protected = set()
        backward = re.compile(r"см[.]?\\s*выше|(?:описан|указан|перечислен)\\w*\\s+выше", re.I)
        forward = re.compile(r"см[.]?\\s*ниже|(?:описан|указан|перечислен)\\w*\\s+ниже", re.I)
        for f in ordered:
            before, after = backward.search(f.text), forward.search(f.text)
            if before or after:
                pivot = self.index[f.source_id]
                for other in ordered:
                    if other.document_id == f.document_id:
                        index = self.index[other.source_id]
                        if (before and index <= pivot) or (after and index >= pivot):
                            protected.add(index)
        # Promote whole selected passages, preserving every source and caveat.
        # This changes only placement: no model/API, no pruning, no added facts.
        selected = set(chosen)
        focus = [i for i in ranked if i in selected and i not in protected][:4]
        focus_ids = {self.fragments[i].source_id for i in focus}
        return ([self.fragments[i] for i in focus] +
                [f for f in ordered if f.source_id not in focus_ids])
'''
assert before.count(old) == 1
p.write_text(before.replace(old, new))
with zipfile.ZipFile(WINNER) as z:
    records = [{'file': f.name,
                'sha256': hashlib.sha256(f.read_bytes()).hexdigest(),
                'changed_from_n2': f.read_bytes() != z.read(f.name)}
               for f in sorted(OUT.iterdir())]
assert [r['file'] for r in records if r['changed_from_n2']] == ['retrieval.py']
(ROOT / 'candidate-manifest.json').write_text(json.dumps({
    'baseline_sha256': EXPECTED, 'records': records,
    'status': 'research_only_not_validated_for_platform'}, indent=2) + '\n')
print(json.dumps({'built': str(OUT), 'changed': ['retrieval.py']}))
