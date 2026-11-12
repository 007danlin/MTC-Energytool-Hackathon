"""Run a frozen list of local ZIP experiments sequentially, stopping on failure.

The plan contains only paths and model metadata; no platform upload is performed.
Completed runs are never overwritten or silently pooled across attempts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf8'))
    endpoint = urlsplit(os.environ.get('LLM_BASE_URL', ''))
    if endpoint.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('This experiment runner is for the authorized local model only')
    kb = ROOT / plan.get('kb', 'data/knowledge-base.zip')
    kb_sha = plan.get('kb_sha256') or digest(kb)
    for job in plan['jobs']:
        archive, questions, output = (ROOT / job[key] for key in ('zip', 'questions', 'output'))
        if (digest(archive) != job['zip_sha256'] or digest(questions) != job['questions_sha256']
                or digest(kb) != kb_sha):
            raise RuntimeError('Frozen experiment input changed: ' + job['name'])
        if output.exists() and any(output.iterdir()):
            raise RuntimeError('Use a new run directory; existing evidence: ' + str(output))
        print(json.dumps({'event': 'job_start', 'name': job['name']}, ensure_ascii=False), flush=True)
        completed = subprocess.run([
            sys.executable, '-u', str(ROOT / 'tools/evaluate_zip_live.py'),
            '--zip', str(archive), '--questions', str(questions),
            '--kb', str(kb), '--expected-kb-sha256', kb_sha,
            '--expected-zip-sha256', job['zip_sha256'],
            '--expected-questions-sha256', job['questions_sha256'],
            '--output', str(output), '--model-label', plan['model_label'],
        ], cwd=ROOT, env=os.environ.copy())
        if completed.returncode:
            print(json.dumps({'event': 'job_failed', 'name': job['name'],
                              'exit_code': completed.returncode}), flush=True)
            return completed.returncode
        summary = json.loads((output / 'summary.json').read_text())
        if not summary['generation_complete'] or not summary['csv_valid']:
            raise RuntimeError('Incomplete generation: ' + job['name'])
        print(json.dumps({'event': 'job_complete', 'name': job['name'],
                          'rows': summary['rows'], 'seconds': summary['elapsed_seconds']},
                         ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
