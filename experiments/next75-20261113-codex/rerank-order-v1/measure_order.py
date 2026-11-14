"""Source preservation and placement audit; never an answer-quality score."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
H = EXP / 'handoff'
sys.dont_write_bytecode = True
sys.path.insert(0, str(H / 'winner/source'))
from consultant import Consultant
from dialogue import retrieval_query
from dialogue_n1 import parse_dialogue
from prompts import render_fragment, render_fragments
from settings import Settings

spec = importlib.util.spec_from_file_location('focus_retrieval', HERE / 'candidate/retrieval.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
KB = H / 'sources/organizers/drive-download-20261109T164943Z-1-001/knowledge-base.zip'
settings = Settings('http://127.0.0.1:1/v1', 'not-a-secret', 'inert-no-network')
base = Consultant(None, KB, settings)
focus = Consultant(None, KB, settings)
focus.wide = candidate.WideRetriever(focus.fragments)
by_id = {f.source_id: f for f in base.fragments}

dev_path = EXP.parents[1] / 'eval/cases_v3.json'
sets = [('known123', json.loads(dev_path.read_text())['cases'])]
with zipfile.ZipFile(H / 'sources/external-agent/mts-n1-handoff-20261112.zip') as z:
    fresh = json.loads(z.read('mts-n1-handoff-20261112/eval/fresh_cases_v1.json'))
    sets.append(('known67', fresh['cases'] if isinstance(fresh, dict) else fresh))
sets.append(('viewed12', json.loads((EXP / 'new-panel-v1.json').read_text())['cases']))

def norm(s):
    return ' '.join(s.lower().replace('ё', 'е').split())

def fact_groups(c):
    if 'required_facts' in c:
        return [[s['source_id'] for s in f['sources']] for f in c['required_facts']]
    out = []
    for ev in c.get('evidence', []):
        if 'source_id' in ev:
            if ev['source_id'] in by_id:
                out.append([ev['source_id']])
        else:
            out.append([f.source_id for f in base.fragments
                        if f.document_id == ev['file'] and norm(ev['quote']) in norm(f.text)])
    return out

rows = []
for name, cases in sets:
    for c in cases:
        messages = parse_dialogue(c['question'])
        query = retrieval_query(messages)
        started = time.perf_counter()
        b, bc = base._build(messages, query, 'docs')
        base_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        n, nc = focus._build(messages, query, 'docs')
        focus_ms = (time.perf_counter() - started) * 1000
        bs = base.wide.search_documents(query, settings.doc_count, settings.doc_k, settings.doc_chars)
        ns = focus.wide.search_documents(query, settings.doc_count, settings.doc_k, settings.doc_chars)
        assert Counter((f.source_id, f.text) for f in bs) == Counter((f.source_id, f.text) for f in ns)
        assert len(bs) == len({f.source_id for f in bs})
        assert b[0] == n[0] and bc == nc
        assert len(b[1]['content']) == len(n[1]['content'])
        # Exact whole-block substitution explains the entire changed user message.
        assert b[1]['content'].replace(render_fragments(bs), render_fragments(ns), 1) == n[1]['content']
        assert [f.source_id for f in focus.wide.search_documents(query)] == [f.source_id for f in ns]
        bp = {f.source_id: i + 1 for i, f in enumerate(bs)}
        np = {f.source_id: i + 1 for i, f in enumerate(ns)}
        # All observed explicit relative dependencies preserve their direction.
        for f in bs:
            i = base.wide.index[f.source_id]
            back = re.search(r'см[.]?\s*выше|(?:описан|указан|перечислен)\w*\s+выше', f.text, re.I)
            forward = re.search(r'см[.]?\s*ниже|(?:описан|указан|перечислен)\w*\s+ниже', f.text, re.I)
            for other in bs:
                if other.document_id != f.document_id:
                    continue
                j = base.wide.index[other.source_id]
                if back and j < i:
                    assert np[other.source_id] < np[f.source_id]
                if forward and j > i:
                    assert np[other.source_id] > np[f.source_id]
        placements = []
        for alternatives in fact_groups(c):
            selected = [sid for sid in alternatives if sid in bp]
            static = [sid for sid in alternatives if base.wide.is_static(by_id[sid].document_id)]
            if selected:
                x, y = min(bp[s] for s in selected), min(np[s] for s in selected)
                placements.append({'alternatives': alternatives, 'static_alternative_present': bool(static),
                                   'baseline_best_position': x, 'candidate_best_position': y,
                                   'direction': 'earlier' if y < x else 'later' if y > x else 'same'})
        rows.append({'set': name, 'id': c['id'], 'source_count': len(bs),
                     'source_set_and_text_preserved': True, 'prompt_character_count_preserved': True,
                     'relative_reference_direction_preserved': True,
                     'prompt_changed': b != n, 'baseline_ids': list(bp), 'candidate_ids': list(np),
                     'prompt_chars': sum(len(m['content']) for m in b),
                     'baseline_messages_sha256': hashlib.sha256(json.dumps(b, ensure_ascii=False).encode()).hexdigest(),
                     'candidate_messages_sha256': hashlib.sha256(json.dumps(n, ensure_ascii=False).encode()).hexdigest(),
                     'baseline_build_ms': base_ms, 'candidate_build_ms': focus_ms,
                     'required_source_placements': placements})
    print(name, len(cases), 'verified', flush=True)

summary = {'kind': 'static_placement_not_model_quality', 'candidate_files': json.loads((HERE / 'candidate-manifest.json').read_text()),
           'dev123_path': str(dev_path), 'dev123_sha256': hashlib.sha256(dev_path.read_bytes()).hexdigest(),
           'kb_sha256': hashlib.sha256(KB.read_bytes()).hexdigest(), 'cases': len(rows),
           'source_preservation_passes': len(rows), 'changed_prompts': sum(r['prompt_changed'] for r in rows),
           'build_time_ms_median': {k: statistics.median(r[k + '_build_ms'] for r in rows) for k in ['baseline', 'candidate']},
           'placements': dict(Counter(p['direction'] for r in rows for p in r['required_source_placements'])),
           'placement_unit': 'annotated required-fact source alternative group with a selected non-static source; overlapping groups are not independent cases',
           'limitations': ['Known/viewed panels, no hidden evaluation.', 'Position changes are not accuracy.',
                          'Many groups also have unchanged static alternatives.', 'Only explicit relative references are guarded.'],
           'rows': rows}
(HERE / 'source-preservation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k not in ('rows', 'candidate_files')}, ensure_ascii=False))
