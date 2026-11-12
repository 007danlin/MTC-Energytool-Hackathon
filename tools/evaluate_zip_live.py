"""Run an immutable submission ZIP against a real API, without a platform upload.

Output is private: it contains organizer questions, model answers and diagnostics.
HTTP observation records only timing/usage; it does not alter requests/responses.
This tool never estimates the organizer's closed judge Score.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
TOOL_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

OBSERVER = '''import hashlib,json,os,resource,runpy,threading,time
from pathlib import Path
import consultant,llm_client,solution
original=llm_client.HTTPTransport.post
lock=threading.Lock()
sequence=0
def observed(self,url,headers,payload,timeout):
    global sequence
    started=time.monotonic()
    record={'request_sha256':hashlib.sha256(payload).hexdigest()}
    try:
        response=original(self,url,headers,payload,timeout)
        record['http_status']=response[0]
        try:
            data=json.loads(response[2])
            record['usage']=data.get('usage',{})
            record['finish_reason']=data.get('choices',[{}])[0].get('finish_reason')
            with lock:
                with (Path(os.environ['LIVE_EVAL_OUTPUT_DIR'])/'model-responses.jsonl').open('a',encoding='utf8') as capture:
                    capture.write(json.dumps({'request_sha256':record['request_sha256'],'choices':data.get('choices',[])},ensure_ascii=False)+'\\n')
        except (ValueError,KeyError,TypeError,IndexError):
            pass
        return response
    except Exception as exc:
        record['error_type']=type(exc).__name__
        raise
    finally:
        record['elapsed_seconds']=round(time.monotonic()-started,3)
        with lock:
            sequence+=1
            record['call']=sequence
            with Path('api-observations.jsonl').open('a',encoding='utf8') as stream:
                stream.write(json.dumps(record)+'\\n')
            print(json.dumps({'event':'observed_api_call',**record}),flush=True)
llm_client.HTTPTransport.post=observed
service_class=solution.Consultant
original_respond=service_class.respond
def observe_case(self,request,**kwargs):
    result=original_respond(self,request,**kwargs)
    record={'session_id':request.session_id,'answer':result.answer,'status':result.status,
            'elapsed_ms':result.elapsed_ms,'debug':result.debug}
    with lock:
        destination=Path(os.environ['LIVE_EVAL_OUTPUT_DIR'])/'case-responses.jsonl'
        with destination.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(record,ensure_ascii=False)+'\\n')
    print(json.dumps({'event':'observed_case','session_id':request.session_id,
                      'status':result.status,'elapsed_ms':result.elapsed_ms}),flush=True)
    return result
service_class.respond=observe_case
try:
    runpy.run_path('solution.py',run_name='__main__')
finally:
    print(json.dumps({'event':'runtime_resource_usage','max_rss_raw':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      'max_rss_unit':'bytes' if __import__('sys').platform=='darwin' else 'KiB'}),flush=True)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--questions', type=Path, default=ROOT / 'data/questions.csv')
    parser.add_argument('--kb', type=Path, default=ROOT / 'data/knowledge-base.zip')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model-label', required=True, help='Human-readable deployment identification; not a key')
    for name in ('zip', 'questions', 'kb'):
        parser.add_argument('--expected-' + name + '-sha256')
    args = parser.parse_args()
    output = args.output.resolve()
    evidence_files = ('summary.json', 'submission.csv', 'case-responses.jsonl',
                      'api-observations.jsonl', 'runtime-stdout.jsonl', 'runtime-stderr.jsonl')
    if any((output / name).exists() for name in evidence_files):
        parser.error('Use a new output directory to preserve previous evidence')
    required = ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL')
    if any(not os.environ.get(name) for name in required):
        parser.error('Export LLM_BASE_URL, LLM_API_KEY and LLM_MODEL before running')
    snapshots = {name: getattr(args, name).read_bytes() for name in ('zip', 'questions', 'kb')}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in snapshots.items()}
    for name, actual in hashes.items():
        expected = getattr(args, 'expected_' + name + '_sha256')
        if expected and expected != actual:
            parser.error('Frozen input changed: ' + name)
    output.mkdir(parents=True, exist_ok=True)
    input_rows = list(csv.DictReader(io.StringIO(snapshots['questions'].decode('utf-8-sig'))))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='energytool-real-zip-') as folder:
        runtime = Path(folder)
        with ZipFile(io.BytesIO(snapshots['zip'])) as archive:
            if any('/' in n or '\\' in n or n.startswith('.') for n in archive.namelist()):
                parser.error('Expected a root-only submission archive')
            archive.extractall(runtime)
        (runtime / 'data').mkdir()
        (runtime / 'data/questions.csv').write_bytes(snapshots['questions'])
        (runtime / 'data/knowledge-base.zip').write_bytes(snapshots['kb'])
        (runtime / '_observe.py').write_text(OBSERVER, encoding='utf8')
        # No inherited Python paths or unrelated credentials in the child process.
        env = {'PATH': os.environ.get('PATH', ''), 'PYTHONIOENCODING': 'utf-8',
               'PYTHONDONTWRITEBYTECODE': '1', 'DATA_DIR': 'data',
               'LIVE_EVAL_OUTPUT_DIR': str(output)}
        names = required + ('TEMPERATURE','MAX_TOKENS','MAX_WORKERS','LLM_TIMEOUT',
                            'LLM_ATTEMPTS','TOP_K','CONTEXT_CHARS','RUN_BUDGET_SECONDS')
        env.update({name: os.environ[name] for name in names if name in os.environ})
        with (output / 'runtime-stderr.jsonl').open('w', encoding='utf8') as errors, \
                (output / 'runtime-stdout.jsonl').open('w', encoding='utf8') as logs:
            process = subprocess.Popen([sys.executable, '-u', '_observe.py'], cwd=runtime,
                                       env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
            try:
                for line in process.stdout:
                    logs.write(line)
                    logs.flush()
                    print(line.rstrip(), flush=True)
                code = process.wait(timeout=30)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        for name in ('submission.csv', 'api-observations.jsonl'):
            if (runtime / name).exists():
                shutil.copyfile(runtime / name, output / name)
    csv_path = output / 'submission.csv'
    if not csv_path.exists():
        raise RuntimeError('Runtime produced no CSV; see private stderr file')
    with csv_path.open(encoding='utf8', newline='') as stream:
        reader = csv.DictReader(stream)
        columns, rows = reader.fieldnames, list(reader)
    observations = [json.loads(line) for line in (output / 'api-observations.jsonl').read_text().splitlines()] \
        if (output / 'api-observations.jsonl').exists() else []
    events = [json.loads(line) for line in (output / 'runtime-stdout.jsonl').read_text().splitlines()]
    stats = next((v for v in reversed(events) if 'statuses' in v), {})
    statuses = stats.get('statuses', {})
    # A well-formed CSV can contain only technical fallbacks. Keep protocol and
    # generation success distinct, so a broken local service fails the run gate.
    generation_complete = bool(rows) and sum(statuses.values()) == len(rows) and all(
        name in {'answered', 'clarification', 'knowledge_gap', 'out_of_scope'}
        for name, count in statuses.items() if count)
    resource_usage = next((v for v in reversed(events) if v.get('event') == 'runtime_resource_usage'), {})
    summary = {
        'mode': 'real_model_immutable_zip', 'model_label': args.model_label,
        'platform_model_verified': False, 'platform_score': None,
        'zip_sha256': hashes['zip'], 'questions_sha256': hashes['questions'],
        'knowledge_base_sha256': hashes['kb'], 'evaluation_tool_sha256': TOOL_SHA256,
        'observer_sha256': hashlib.sha256(OBSERVER.encode()).hexdigest(),
        'rows': len(rows), 'exit_code': code, 'elapsed_seconds': round(time.monotonic()-started,2),
        'csv_valid': columns == ['id','answer'] and [r['id'] for r in rows] == [r['id'] for r in input_rows]
                     and all(0 < len(r['answer']) <= 10000 for r in rows),
        'runtime_statuses': statuses, 'generation_complete': generation_complete,
        'resource_usage': resource_usage, 'api_calls': len(observations),
        'http_failures': sum(r.get('http_status') != 200 for r in observations),
        'length_cutoffs': sum(r.get('finish_reason') == 'length' for r in observations),
        'content_review_complete': False,
        'note': 'Nonempty CSV is not evidence of factual quality; inspect answers against the knowledge base.',
    }
    (output / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if code == 0 and summary['csv_valid'] and generation_complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
