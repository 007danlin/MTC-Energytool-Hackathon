"""Validate the expert-review ZIP, not the automatic ML submission."""
import argparse, hashlib, json, re, zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
def validate(path):
 with zipfile.ZipFile(path) as z:
  names=z.namelist()
  assert len(names)==len(set(names)), 'Duplicate archive entries'
  assert z.testzip() is None, 'ZIP CRC failure'
  for name in names:
   parts=PurePosixPath(name).parts
   assert not name.startswith('/') and '..' not in parts, 'Unsafe archive path'
   assert not any(p in {'.git','.venv','node_modules','__pycache__'} for p in parts), name
   assert PurePosixPath(name).name not in {'.env','.env.web','.env.local','sessions.json','expert-kb.json'}, name
  required=['README.md','EnergyTool-презентация.pdf','project/README.md',
            'project/Dockerfile','project/Dockerfile.web','project/compose.yaml',
            'project/.dockerignore','project/.env.example','project/.env.web.example',
            'project/requirements.txt','project/backend/go.mod','project/backend/Dockerfile',
            'project/data/knowledge-base.zip','demo/demo.mp4','SOURCE_REVISION.txt']
  assert all(n in names for n in required), 'Required delivery file missing'
  manifest=json.loads(z.read('SHA256.json'))
  assert set(manifest)==set(names)-{'SHA256.json'}, 'Manifest does not cover exact archive'
  for name,digest in manifest.items():
   assert hashlib.sha256(z.read(name)).hexdigest()==digest, name
  original=ROOT/'deliverables/2026-11-15/Energytool_presentation_MTS_style.pdf'
  assert z.read('EnergyTool-презентация.pdf')==original.read_bytes(), 'Presentation modified'
  assert z.read('ml-submit/N2-победивший-сабмит.zip')==(ROOT/'artifacts/mts-energytool-n2-docs.zip').read_bytes(), 'Frozen N2 changed'
  # Compare against configured long secrets locally; never emit their values.
  secrets=[]
  env=ROOT/'.env.web'
  if env.exists():
   for line in env.read_text().splitlines():
    if '=' in line:
     key,value=line.split('=',1);value=value.strip().strip('\"\'')
     if ('KEY' in key or 'TOKEN' in key or 'PASSWORD' in key) and len(value)>=16:
      secrets.append(value.encode())
  for name in names:
   if Path(name).suffix.lower() not in {'.py','.md','.txt','.json','.log','.yaml','.yml','.js','.cjs','.html','.example'}:continue
   data=z.read(name)
   assert not any(secret in data for secret in secrets), 'Configured secret in '+name
   assert not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}',data), 'Credential pattern in '+name
 return {'status':'passed','files':len(names),'bytes':path.stat().st_size,
         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'checks':['required files','safe paths','CRC','complete SHA256 inventory',
                   'unchanged original PDF','unchanged frozen N2','credential scan']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('archive',type=Path);a=p.parse_args()
 print(json.dumps(validate(a.archive),ensure_ascii=False))
