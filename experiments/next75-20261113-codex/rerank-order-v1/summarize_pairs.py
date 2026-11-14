"""Summarize every attempt and emit a label-blinded packet for completed pairs."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
LIVE = HERE / 'live'

def read(p):
    return json.loads(p.read_text())

def main():
    panel = read(HERE / 'panel.json')
    cases = {c['id']: c for c in panel['cases']}
    manifest = read(LIVE / 'manifest.json')
    variants = {}
    attempts = []
    results = []
    for run in sorted(p for p in LIVE.iterdir() if p.is_dir()):
        for f in sorted((run / 'http').glob('*.metadata.json')):
            meta = read(f)
            request = f.with_name(f.name.replace('.metadata.json', '.request.bin'))
            assert hashlib.sha256(request.read_bytes()).hexdigest() == meta['request_sha256']
            response = f.with_name(f.name.replace('.metadata.json', '.response.bin'))
            if response.exists() and meta.get('response_sha256'):
                assert hashlib.sha256(response.read_bytes()).hexdigest() == meta['response_sha256']
            attempts.append({'run': run.name, 'path': str(f.relative_to(HERE)), **meta})
        f = run / 'generation/result.json'
        if not f.exists():
            continue
        inp = read(run / 'generation/input.json')
        result = read(f)
        variant = 'n2' if inp['source'].endswith('/handoff/winner/source') else 'focus'
        results.append({'run': run.name, 'variant': variant, **result})
        if (result.get('answer') and not result.get('aborted') and
                result.get('info', {}).get('status') not in ('fallback', 'deadline_fallback', 'partial')):
            variants.setdefault(result['case'], {})[variant] = (result, run)
    rng = random.Random(2026111307)
    packet = {'instructions': 'Judge only completed pairs from full dialogue and supplied evidence. Assess direct answer, all decisive conditions, history, next step, and every new unsupported claim. Do not reward length. Return A/B/tie/uncertain with exact factual reasons. No platform Score or generalization claim.', 'pairs': []}
    mapping = {'pairs': [], 'incomplete': []}
    for case_id in ('hold01', 'hold17', 'n11', 'bill17'):
        pair = variants.get(case_id, {})
        if set(pair) != {'n2', 'focus'}:
            mapping['incomplete'].append(case_id)
            continue
        labels = ['n2', 'focus']
        rng.shuffle(labels)
        c = cases[case_id]
        packet['pairs'].append({**c, 'answers': {label: pair[v][0]['answer'] for label, v in zip(('A', 'B'), labels)}})
        payloads = {v: json.loads(next((run / 'http').glob('*.request.bin')).read_bytes()) for v, (_, run) in pair.items()}
        b, n = payloads['n2'], payloads['focus']
        bkw, nkw = ({k: val for k, val in d.items() if k != 'messages'} for d in (b, n))
        assert bkw == nkw
        assert b['messages'][0] == n['messages'][0]
        assert len(b['messages'][1]['content']) == len(n['messages'][1]['content'])
        # Entire source blocks are compared, and the final dialogue suffix is equal.
        bprefix, bdialogue = b['messages'][1]['content'].rsplit('\n\nДИАЛОГ\n', 1)
        nprefix, ndialogue = n['messages'][1]['content'].rsplit('\n\nДИАЛОГ\n', 1)
        assert bdialogue == ndialogue
        assert Counter(bprefix.split('\n\n[Раздел: ')) == Counter(nprefix.split('\n\n[Раздел: '))
        mapping['pairs'].append({'id': case_id, 'labels': dict(zip(('A', 'B'), labels)),
                                  'identical_answers': pair['n2'][0]['answer'] == pair['focus'][0]['answer'],
                                  'actual_first_http_kwargs_equal': True, 'actual_first_http_source_blocks_equal': True})
    (HERE / 'blind').mkdir(exist_ok=True)
    for filename, data in [('packet.json', packet), ('mapping.json', mapping)]:
        (HERE / 'blind' / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    summary = {'status': manifest['status'], 'completed_pairs': len(mapping['pairs']),
               'complete_generation_records': len(results), 'http_attempts': len(attempts),
               'incomplete_pairs': mapping['incomplete'], 'all_attempts': attempts, 'all_results': results,
               'not_quality_judgment': True, 'not_platform_batch': True}
    (HERE / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('all_attempts', 'all_results')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
