"""Freeze the authorized web delta, preserving the user's initial working tree."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
OUT = EXP / 'web-debug-audit'
VALIDATION = json.loads((OUT / 'validation.json').read_text())
files = set(VALIDATION['source_hashes'])
# Include all touched tracked files in the owned scope, excluding platform
# results and other unrelated work. The initial user UI state is the baseline.
owned = ('backend/', 'docs/', 'tests/', 'tools/host_tests/', 'local-preview/energytool-site/')
for command in (['git', 'diff', '--name-only'], ['git', 'ls-files', '--others', '--exclude-standard']):
    output = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout
    for name in output.splitlines():
        if name in ('consultant.py', 'prompts.py') or name.startswith(owned):
            files.add(name)
records, patches = [], []
for name in sorted(files):
    p = ROOT / name
    if not p.is_file():
        raise RuntimeError('Missing expected task source: ' + name)
    raw = p.read_bytes()
    target = OUT / 'current-source' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    baseline = OUT / 'baseline' / name
    if baseline.exists():
        before, origin = baseline.read_bytes(), 'preexisting-user-state'
    else:
        result = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=ROOT, capture_output=True)
        before = result.stdout if result.returncode == 0 else b''
        origin = 'git-HEAD' if result.returncode == 0 else 'new-file'
    old = OUT / 'before-source' / name
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(before)
    delta = difflib.unified_diff(before.decode().splitlines(keepends=True),
        raw.decode().splitlines(keepends=True), fromfile='a/' + name if origin != 'new-file' else '/dev/null',
        tofile='b/' + name)
    # difflib omits the marker required by patch/git for files without a final
    # newline. Keep the actual before/after bytes, including that distinction.
    patches.append(''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                           for line in delta))
    records.append({'path': name, 'before_origin': origin,
                    'before_sha256': hashlib.sha256(before).hexdigest(),
                    'after_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                    'changed_by_this_task': raw != before})
(OUT / 'debug-changes.patch').write_text(''.join(patches))
(OUT / 'source-package-manifest.json').write_text(json.dumps({
    'files': records, 'note': 'Patch applies to each stated before state. Full snapshots preserve preexisting user UI edits. Do not blindly overwrite later edits.'},
    ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'files': len(records), 'changed_by_this_task': sum(r['changed_by_this_task'] for r in records),
                  'patch_bytes': (OUT / 'debug-changes.patch').stat().st_size}))
