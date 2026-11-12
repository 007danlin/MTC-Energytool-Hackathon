"""Rebuild only the runtime file allowlist inherited from frozen A2."""
import ast,hashlib,json
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
baseline=ROOT/'artifacts/daniel-submission-a2.zip'
assert hashlib.sha256(baseline.read_bytes()).hexdigest()=='fa81606a5e4b89cd4b36a13139d906e8940bbc462d43d127ddfaac129c50f013'
with ZipFile(baseline) as z: names=sorted(z.namelist())
output=ROOT/'artifacts/daniel-submission-a5-contact-experimental.zip'
with ZipFile(output,'w',ZIP_DEFLATED) as z:
 for name in names:
  raw=(HERE/name).read_bytes()
  if name.endswith('.py'): ast.parse(raw)
  info=ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
  z.writestr(info,raw)
manifest={'zip':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':names,'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest()}
output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
