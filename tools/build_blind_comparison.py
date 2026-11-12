"""Build a source-grounded A/B packet without exposing strategy names to reviewers."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'candidate', 'questions', 'rubric', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    args = parser.parse_args()
    packet_path = args.output.with_suffix('.packet.json')
    mapping_path = args.output.with_suffix('.mapping.json')
    if packet_path.exists() or mapping_path.exists():
        parser.error('Do not overwrite frozen blind packets')
    questions, control, candidate = map(rows, (args.questions, args.control, args.candidate))
    ids = [r['id'] for r in questions]
    if len(set(ids)) != len(ids) or any([r['id'] for r in answer] != ids for answer in (control, candidate)):
        parser.error('Input and answer IDs must be unique and match in order')
    rubric = json.loads(args.rubric.read_text(encoding='utf8'))
    criteria = {case['id']: case for case in rubric['cases']}
    if set(criteria) != set(ids):
        parser.error('Rubric cases must match questions')
    safe_fields = ('topic', 'task_family', 'family', 'required_criteria',
                   'conditional_criteria', 'critical_failures', 'unknown_handling',
                   'insufficient_information_behavior', 'acceptable_variations',
                   'history_requirements', 'source_ids', 'source_evidence')
    rng = random.Random(args.seed)
    cases, mapping = [], []
    for question, left, right in zip(questions, control, candidate):
        criterion = criteria[question['id']]
        if criterion.get('question', question['question']) != question['question']:
            parser.error('Question differs from preregistered rubric')
        control_first = bool(rng.getrandbits(1))
        cases.append({'id': question['id'], 'question': question['question'],
                      'criteria': {key: criterion[key] for key in safe_fields if key in criterion},
                      'answer_a': left['answer'] if control_first else right['answer'],
                      'answer_b': right['answer'] if control_first else left['answer']})
        mapping.append({'id': question['id'], 'control_side': 'A' if control_first else 'B'})
    packet = {
        'method': 'Blind paired review against provided sources; not platform judge',
        'instructions': [
            'Review the whole current question and history, not word overlap with an example answer.',
            'Grade each side good, partial, or major; record winner A, B, or tie.',
            'A material unsupported claim or contradiction cannot be compensated by fluent style.',
            'An appropriate unknown-fact response is valid; refusal despite available evidence is not.',
            'Check unexpected factual claims against the full local KB before calling them unsupported.',
            'Apply the same conditions to both sides; do not require unrelated warnings.',
            'Explain each major issue with answer quote and supporting source IDs.',
            'Output cases with id,winner,a_status,b_status,reason,critical_evidence; do not inspect mapping.',
        ],
        'questions_sha256': sha(args.questions), 'rubric_sha256': sha(args.rubric), 'cases': cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    mapping_path.write_text(json.dumps({
        'seed': args.seed, 'control_csv': str(args.control), 'candidate_csv': str(args.candidate),
        'control_sha256': sha(args.control), 'candidate_sha256': sha(args.candidate),
        'packet_sha256': sha(packet_path), 'cases': mapping,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'packet': str(packet_path), 'cases': len(cases), 'sha256': sha(packet_path)}))


if __name__ == '__main__':
    main()
