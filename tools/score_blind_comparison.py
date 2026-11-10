"""Unblind a complete human/source review; never infer a platform Score."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def score(mapping, review):
    if mapping.get('packet_sha256') and review.get('packet_sha256') != mapping['packet_sha256']:
        raise ValueError('Review must identify the exact blind packet SHA-256')
    mapped = {r['id']: r['control_side'] for r in mapping['cases']}
    cases = review['cases']
    ids = [r['id'] for r in cases]
    if len(set(ids)) != len(ids) or set(ids) != set(mapped):
        raise ValueError('Review must cover every case exactly once')
    result = []
    for row in cases:
        if row['winner'] not in {'A', 'B', 'tie'}:
            raise ValueError('Unknown winner')
        if any(row[key] not in {'good', 'partial', 'major'} for key in ('a_status', 'b_status')):
            raise ValueError('Unknown grade')
        control = mapped[row['id']].lower()
        candidate = 'b' if control == 'a' else 'a'
        outcome = ('tie' if row['winner'] == 'tie' else
                   'loss' if row['winner'].lower() == control else 'win')
        result.append({'id': row['id'], 'outcome': outcome,
                       'control_status': row[control + '_status'],
                       'candidate_status': row[candidate + '_status'],
                       'reason': row['reason'],
                       'critical_evidence': row.get('critical_evidence', [])})
    outcomes = Counter(r['outcome'] for r in result)
    return {
        'method': 'Unblinded source-grounded paired review; not platform judge',
        'n': len(result), 'wins': outcomes['win'], 'ties': outcomes['tie'],
        'losses': outcomes['loss'], 'net_wins': outcomes['win'] - outcomes['loss'],
        'control_grades': dict(Counter(r['control_status'] for r in result)),
        'candidate_grades': dict(Counter(r['candidate_status'] for r in result)),
        'new_major_ids': [r['id'] for r in result if r['candidate_status'] == 'major'
                          and r['control_status'] != 'major'],
        'cases': result, 'platform_score_prediction': None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('mapping', 'review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve previous decisions; use a new output')
    mapping = json.loads(args.mapping.read_text(encoding='utf8'))
    review = json.loads(args.review.read_text(encoding='utf8'))
    result = score(mapping, review)
    result.update(control_csv=mapping['control_csv'], candidate_csv=mapping['candidate_csv'],
                  review_sha256=hashlib.sha256(args.review.read_bytes()).hexdigest(),
                  mapping_sha256=hashlib.sha256(args.mapping.read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in result.items() if key != 'cases'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
