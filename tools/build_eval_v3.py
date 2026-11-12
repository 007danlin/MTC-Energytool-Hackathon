"""Build eval/cases_v3.json from eval/cases_v2.json + tools/eval_annotations_v3.py.

Validates that every alternative source of every fact contains one of the fact's
key phrases (after normalization) and stores the matching passage as a quote.
Fails loudly on any unsupported source, unknown reference or missing case.

Usage: python tools/build_eval_v3.py [--kb data/knowledge-base.zip]
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from retrieval import load_fragments  # noqa: E402
import eval_annotations_v3 as ann  # noqa: E402

DOCS = {
    'PM': '00-reference/00-product-map.md', 'N': '00-reference/01-numbers-and-indicators.md',
    'SC': '00-reference/02-product-scope-and-limits.md', 'CR': '00-reference/03-calculation-and-requests.md',
    'MK': '10-energy/10-market.md', 'PC': '10-energy/11-price-categories.md',
    'PT': '10-energy/12-power-thresholds.md', 'MT': '10-energy/13-metering.md',
    'TR': '10-energy/14-tariffs.md', 'MG': '10-energy/15-microgeneration.md',
    'RG': '10-energy/16-regulation.md', 'FQ': '10-energy/17-faq.md',
    'PF': '20-products/20-portfolio.md', 'O': '20-products/21-orem.md', 'A': '20-products/22-askue.md',
    'S': '20-products/23-solar.md', 'L': '20-products/24-losses.md',
    'P': '20-products/25-meter-reading.md', 'G': '20-products/26-general.md',
}


def sid(ref):
    key = ref.rstrip('0123456789')
    return f"{DOCS[key]}#s{int(ref[len(key):]):03d}"


def norm(text):
    text = text.lower().replace('ё', 'е').replace('₽', 'руб')
    text = re.sub(r'[*`]', '', text)
    text = re.sub(r'-{2,}|[–—]', '-', text)
    return re.sub(r'\s+', ' ', text).strip()


def quote(text, keys):
    body = norm(text.split('\n', 1)[-1])
    for key in keys:
        pos = body.find(key)
        if pos >= 0:
            start = max(0, body.rfind('. ', 0, pos) + 2 if body.rfind('. ', 0, pos) >= 0 else 0, pos - 160)
            end = body.find('. ', pos + len(key))
            end = len(body) if end < 0 or end - pos > 220 else end + 1
            return body[start:end].strip()
    return None


def resolve(item, frags, errors, cid, kind):
    out = {k: v for k, v in item.items() if k not in ('refs', 'keys')}
    sources = []
    for ref in item['refs']:
        try:
            source_id = sid(ref)
        except (KeyError, ValueError):
            errors.append(f'{cid} {kind}: bad ref {ref}')
            continue
        if source_id not in frags:
            errors.append(f'{cid} {kind}: unknown source {source_id}')
            continue
        if 'keys' in item:
            q = quote(frags[source_id], [norm(k) for k in item['keys']])
            if q is None:
                errors.append(f'{cid} {kind} «{item["fact"][:50]}»: {source_id} has none of {item["keys"]}')
                continue
            sources.append({'source_id': source_id, 'quote': q})
        else:
            sources.append({'source_id': source_id})
    out['sources'] = sources
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--kb', default=str(ROOT / 'data/knowledge-base.zip'))
    p.add_argument('--base', default=str(ROOT / 'eval/cases_v2.json'))
    p.add_argument('--output', default=str(ROOT / 'eval/cases_v3.json'))
    args = p.parse_args()

    frags = {f.source_id: f.text for f in load_fragments(args.kb)}
    base = json.loads(Path(args.base).read_text(encoding='utf8'))
    missing = sorted({c['id'] for c in base} - set(ann.CASES)) + sorted(set(ann.CASES) - {c['id'] for c in base})
    if missing:
        raise SystemExit(f'Annotation/case mismatch: {missing}')

    errors, cases = [], []
    for c in base:
        a = ann.CASES[c['id']]
        req = [resolve(x, frags, errors, c['id'], 'required') for x in a.get('req', [])]
        cond = [resolve(x, frags, errors, c['id'], 'conditional') for x in a.get('cond', [])]
        forbid = [resolve(x, frags, errors, c['id'], 'forbidden') for x in a.get('forbid', [])]
        cases.append({
            'id': c['id'], 'split': c['split'], 'topic': c['topic'], 'type': c['type'], 'question': c['question'],
            'expected': c['expected'],
            'required_facts': req, 'conditional_facts': cond, 'forbidden_claims': forbid,
            'acceptable_unknowns': a.get('unk', []),
            # Compatibility with tools/retrieval_benchmark.py: one group per required fact (AND), sources OR.
            'groups': [[s['source_id'] for s in f['sources']] for f in req],
            'review': {'artem': 'commented' if c['id'] in ann.ARTEM_COMMENTED else 'no_remarks',
                       'kb_quotes': 'verified_by_script'},
            'note': '; '.join(x for x in (c.get('note', ''), a.get('note', '')) if x),
        })
    if errors:
        print('\n'.join(errors))
        raise SystemExit(f'{len(errors)} unsupported sources')

    kb_sha = hashlib.sha256(Path(args.kb).read_bytes()).hexdigest()
    ann_sha = hashlib.sha256((ROOT / 'tools/eval_annotations_v3.py').read_bytes()).hexdigest()
    doc = {'version': 3, 'knowledge_base_sha256': kb_sha, 'annotations_sha256': ann_sha,
           'holdout_note': 'split=holdout уже использовался в экспериментах 10–11.11; не является новым независимым контролем',
           'cases': cases}
    out = Path(args.output)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    # Flat list (id/question/groups) for tools/retrieval_benchmark.py --cases
    (ROOT / 'data/eval').mkdir(parents=True, exist_ok=True)
    (ROOT / 'data/eval/retrieval_cases_v3.json').write_text(
        json.dumps([{k: c[k] for k in ('id', 'split', 'topic', 'type', 'question', 'groups')} for c in cases],
                   ensure_ascii=False, indent=1), encoding='utf8')
    n_req = sum(len(c['required_facts']) for c in cases)
    n_src = sum(len(f['sources']) for c in cases for f in c['required_facts'] + c['conditional_facts'])
    print(f'{len(cases)} cases, {n_req} required facts, {sum(len(c["conditional_facts"]) for c in cases)} conditional, '
          f'{sum(len(c["forbidden_claims"]) for c in cases)} forbidden; {n_src} verified source quotes')
    print('kb', kb_sha[:16], 'annotations', ann_sha[:16], '->', out)


if __name__ == '__main__':
    main()
