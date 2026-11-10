"""Private source-level retrieval audit; never included in the submitted ZIP.

Labels are evidence-source IDs, not answers. Each group represents a separate
fact; alternatives within a group are equivalent evidence. This is a diagnostic
on public demo questions, not a held-out quality estimate or LLM judge score.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from types import ModuleType
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sources(doc, *chunks):
    return [doc + '#s' + str(c).zfill(3) for c in chunks]

S = '20-products/23-solar.md'
A = '20-products/22-askue.md'
P = '20-products/25-meter-reading.md'
L = '20-products/24-losses.md'
O = '20-products/21-orem.md'
R = '00-reference/03-calculation-and-requests.md'
LABELS = {
    '1': [sources(S, 9)], '2': [sources(S, 9)],
    '3': [sources(S, 4)], '4': [sources(S, 7)],
    '5': [sources(A, 15)], '6': [sources(A, 2, 3)],
    '7': [sources(A, 3, 8) + sources('20-products/20-portfolio.md', 9)],
    '8': [sources(P, 5), sources(P, 11, 14)],
    '9': [sources(P, 5)], '10': [sources('10-energy/14-tariffs.md', 1)],
    '11': [sources('10-energy/17-faq.md', 4)],
    '12': [sources(O, 10, 14), sources(O, 3) + sources('00-reference/01-numbers-and-indicators.md', 1)],
    '13': [sources(O, 18) + sources('20-products/26-general.md', 18) + sources(R, 1)],
    '14': [sources(S, 5, 7, 8), sources(S, 8, 23)],
    '15': [sources(P, 3), sources(A, 2, 3), sources(R, 6)],
    '16': [sources(L, 9, 19) + sources(R, 7), sources(L, 6, 10, 19, 20)],
    '17': [sources('10-energy/14-tariffs.md', 1), sources('10-energy/11-price-categories.md', 4)],
    '18': [sources(R, 6)],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', default=str(ROOT / 'retrieval.py'))
    parser.add_argument('--dialogue-module', default=str(ROOT / 'dialogue.py'))
    parser.add_argument('--baseline-zip', help='Load exactly retrieval.py and dialogue.py from a saved submission')
    parser.add_argument('--kb', default=str(ROOT / 'data/knowledge-base.zip'))
    parser.add_argument('--questions', default=str(ROOT / 'data/questions.csv'))
    parser.add_argument('--cases', help='Optional JSON array of independently written question/evidence groups')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.baseline_zip:
        with ZipFile(args.baseline_zip) as archive:
            retrieval_code = archive.read('retrieval.py')
            dialogue_code = archive.read('dialogue.py')
    else:
        retrieval_code = Path(args.module).read_bytes()
        dialogue_code = Path(args.dialogue_module).read_bytes()
    module = ModuleType('audited_retrieval')
    dialogue = ModuleType('audited_dialogue')
    exec(compile(retrieval_code, 'audited_retrieval.py', 'exec'), module.__dict__)
    exec(compile(dialogue_code, 'audited_dialogue.py', 'exec'), dialogue.__dict__)
    retriever = module.LexicalRetriever.from_zip(args.kb)
    results = []
    if args.cases:
        rows = json.loads(Path(args.cases).read_text(encoding='utf8'))
    else:
        with open(args.questions, encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
    for row in rows:
        fragments = retriever.search(dialogue.retrieval_query(dialogue.parse_question(row['question'])))
        ids = [f.source_id for f in fragments]
        groups = row['groups'] if 'groups' in row else LABELS[row['id']]
        ranks = [min((ids.index(s) + 1 for s in group if s in ids), default=None) for group in groups]
        results.append({'id': row['id'], 'ranks': ranks, 'sources': ids,
                        'chars': sum(len(f.text) for f in fragments), 'fragments': len(fragments)})
    ranks = [rank for row in results for rank in row['ranks']]
    lengths = sorted(row['chars'] for row in results)
    summary = {'questions': len(results), 'evidence_groups': len(ranks),
               'coverage': {str(k): round(sum(r is not None and r <= k for r in ranks) / len(ranks), 4) for k in (1, 3, 6, 12)},
               'coverage_full': round(sum(r is not None for r in ranks) / len(ranks), 4),
               'all_groups_top12': sum(all(r is not None and r <= 12 for r in row['ranks']) for row in results),
               'context_chars_median': statistics.median(lengths),
               'context_chars_p95': lengths[math.ceil(len(lengths) * .95) - 1],
               'p95_method': 'nearest-rank: sorted_values[ceil(0.95*N)-1]',
               'context_chars_mean': round(statistics.mean(lengths)),
               'fragments_mean': round(statistics.mean(row['fragments'] for row in results), 1)}
    sha = lambda content: hashlib.sha256(content).hexdigest()
    groups = {row['id']: row.get('groups', LABELS.get(row['id'])) for row in rows}
    provenance = {
        'knowledge_base_sha256': sha(Path(args.kb).read_bytes()),
        'question_file_sha256': sha(Path(args.cases or args.questions).read_bytes()),
        'retrieval_py_sha256': sha(retrieval_code),
        'dialogue_py_sha256': sha(dialogue_code),
        'evidence_groups_sha256': sha(json.dumps(groups, ensure_ascii=False, sort_keys=True).encode('utf8')),
        'baseline_zip_sha256': sha(Path(args.baseline_zip).read_bytes()) if args.baseline_zip else None,
        'benchmark_py_sha256': sha(Path(__file__).read_bytes()),
        'top_k': 12,
    }
    Path(args.output).write_text(json.dumps({'summary': summary, 'provenance': provenance, 'results': results},
                                          ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for row in results:
        print(row['id'], row['ranks'], row['chars'])


if __name__ == '__main__':
    main()
