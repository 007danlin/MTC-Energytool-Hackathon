"""Serial real-model order-only comparison; no synthetic failures or remote API."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
EXP = HERE.parent

def write(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--budget-seconds', type=float, default=3600)
    a = p.parse_args()
    out = HERE / 'live'
    out.mkdir(exist_ok=False)
    assert json.loads((HERE / 'source-preservation.json').read_text())['cases'] == 202
    sources = {'n2': EXP / 'handoff/winner/source', 'focus': HERE / 'candidate'}
    cases = ('hold01', 'hold17', 'n11', 'bill17')
    ordered = [(case, v) for i, case in enumerate(cases)
               for v in (('n2', 'focus') if i % 2 == 0 else ('focus', 'n2'))]
    manifest = {'kind': 'source_order_only_real_model_diagnostic', 'status': 'running',
                'not_platform_batch': True, 'synthetic_prefix': False,
                'model': a.model, 'ordered_runs': ordered, 'completed': [],
                'wall_budget_seconds': a.budget_seconds, 'started_unix': time.time(),
                'panel_sha256': hashlib.sha256((HERE / 'panel.json').read_bytes()).hexdigest(),
                'harness_sha256': {str(p.relative_to(EXP)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (Path(__file__), EXP / 'generate_diagnostic_case.py', EXP / 'http_trace_proxy.py')},
                'caveat': 'Qwen3.8 community 4-bit local diagnostic; hidden provider configuration differs; known selected error families.'}
    mf = out / 'manifest.json'
    write(mf, manifest)
    deadline = time.monotonic() + a.budget_seconds
    start = time.monotonic()
    try:
        for number, (case, variant) in enumerate(ordered, 1):
            if time.monotonic() >= deadline:
                manifest['status'] = 'wall_budget_exhausted'
                break
            run = out / ('%02d-%s-%s' % (number, case, variant))
            run.mkdir()
            with (run / 'proxy.log').open('w') as log:
                proxy = subprocess.Popen([sys.executable, str(EXP / 'http_trace_proxy.py'),
                    '--upstream', 'http://127.0.0.1:18765', '--out', str(run / 'http')],
                    stdout=log, stderr=subprocess.STDOUT)
                try:
                    for _ in range(100):
                        if (run / 'http/port.txt').exists():
                            break
                        if proxy.poll() is not None:
                            raise RuntimeError('recorder_start_failure')
                        time.sleep(.05)
                    port = (run / 'http/port.txt').read_text().strip()
                    cmd = [sys.executable, str(EXP / 'generate_diagnostic_case.py'),
                           '--source', str(sources[variant]), '--panel', str(HERE / 'panel.json'),
                           '--case', case, '--kb', str(EXP / 'n2-test-reference/data/knowledge-base.zip'),
                           '--model', a.model, '--base-url', 'http://127.0.0.1:' + port + '/v1',
                           '--out', str(run / 'generation')]
                    print(json.dumps({'event': 'start', 'run': number, 'case': case, 'variant': variant}), flush=True)
                    began = time.monotonic()
                    with (run / 'stdout.log').open('w') as stdout, (run / 'stderr.log').open('w') as stderr:
                        child = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
                        try:
                            status = {'exit_code': child.wait(timeout=min(1250, max(1, deadline - time.monotonic())))}
                        except subprocess.TimeoutExpired:
                            status = {'timeout': True}
                        finally:
                            if child.poll() is None:
                                child.kill()
                                child.wait()
                    status.update(run=number, case=case, variant=variant, elapsed_seconds=time.monotonic() - began)
                    write(run / 'runner-result.json', status)
                    manifest['completed'].append(status)
                    write(mf, manifest)
                    print(json.dumps({'event': 'done', **status}), flush=True)
                    if status.get('exit_code') != 0:
                        manifest['status'] = 'stopped_after_failed_case'
                        break
                    result = json.loads((run / 'generation/result.json').read_text())
                    if result['info']['status'] in ('fallback', 'deadline_fallback', 'partial'):
                        manifest['status'] = 'stopped_after_unusable_case'
                        break
                finally:
                    proxy.terminate()
                    proxy.wait(timeout=10)
                    for f in (run / 'http').glob('*.metadata.json'):
                        info = json.loads(f.read_text())
                        if info.get('state') == 'started':
                            info.update(state='recorder_terminated', upstream_completion_unknown=True)
                            write(f, info)
        else:
            manifest['status'] = 'complete'
    except KeyboardInterrupt:
        manifest['status'] = 'interrupted'
        raise
    except Exception as exc:
        manifest.update(status='harness_error', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        manifest['elapsed_seconds'] = time.monotonic() - start
        manifest['finished_unix'] = time.time()
        write(mf, manifest)

if __name__ == '__main__':
    main()
