"""Build the final project bundle, excluding live state, credentials and research exports."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(destination):
 stage=destination/'EnergyTool-final-2026-11-15';project=stage/'project'
 if stage.exists():shutil.rmtree(stage)
 project.mkdir(parents=True)
 roots=['backend','local-preview/energytool-site','tests','tools','eval','docs','deliverables','experiments/n2-docs-20261112']
 skip={'__pycache__','node_modules','.venv','.git','var','private','tmp','output'}
 files=[p for p in ROOT.iterdir() if p.is_file() and (p.suffix in ('.py','.yaml') or p.name in ('README.md','Dockerfile','Dockerfile.web','.dockerignore','.gitignore','.env.example','.env.web.example','.env.local.example','requirements.txt'))]
 for root in roots:
  for p in (ROOT/root).rglob('*'):
   if p.is_file() and not(set(p.relative_to(ROOT/root).parts)&skip) and p.suffix not in ('.pyc','.log','.webm','.mp4') and p!=ROOT/'backend/api':files.append(p)
 files += [ROOT/'artifacts/mts-energytool-n2-docs.zip',ROOT/'data/knowledge-base.zip']
 for p in files:
  out=project/p.relative_to(ROOT);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
 # Only synthetic release records; never sessions.json or private model captures.
 checks=project/'reports/release-validation';checks.mkdir(parents=True,exist_ok=True)
 src=ROOT/'reports/release-validation'
 for p in src.rglob('*'):
  if not p.is_file() or 'video' in p.parts or 'benchmark' in p.relative_to(src).parts:continue
  if p.suffix not in ('.json','.png','.log'):continue
  out=checks/p.relative_to(src);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
 shutil.copy2(ROOT/'deliverables/2026-11-15/Energytool_presentation_MTS_style_final.pdf',stage/'EnergyTool-презентация.pdf')
 (stage/'ml-submit').mkdir();shutil.copy2(ROOT/'artifacts/mts-energytool-n2-docs.zip',stage/'ml-submit/N2-победивший-сабмит.zip')
 if (ROOT/'deliverables/2026-11-14/demo.mp4').exists():
  (stage/'demo').mkdir();shutil.copy2(ROOT/'deliverables/2026-11-14/demo.mp4',stage/'demo/demo.mp4')
  shutil.copy2(ROOT/'deliverables/2026-11-14/demo-README.txt',stage/'demo/README.txt')
 (stage/'НАЧНИТЕ-ЗДЕСЬ.txt').write_text('''Финальная сдача EnergyTool: код, документы, PDF и запись демонстрации.

1. Прочитайте презентацию EnergyTool-презентация.pdf.
2. Исходники и инструкция запуска: project/README.md.
3. В project создайте .env.web из .env.web.example и впишите ВЫДАННЫЕ адрес, ключ и идентификатор модели. База организаторов приложена для закрытой проверки в project/data. Не публикуйте комплект открыто.
4. Из project выполните: docker compose up --build -d
5. Откройте http://127.0.0.1:8768/consultation.html
6. Без API модели посмотрите demo/demo.mp4. Запись использует реальную локальную модель, тестовый контакт и отдельное хранилище.

ml-submit/N2-победивший-сабмит.zip — неизменённый архив автоматического этапа. Не загружайте весь этот комплект вместо ML-сабмита: это разные этапы.

Фактические проверки и ограничения: project/docs/release-readiness.md.
Ключей и реальной пользовательской истории в комплекте нет. Доступ к приватному GitHub жюри не открывался: выбран разрешённый регламентом формат ZIP.
''',encoding='utf-8')
 inventory={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(stage.rglob('*')) if p.is_file()}
 (stage/'SHA256.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))
 archive=destination/'EnergyTool-final-2026-11-15.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  for p in sorted(stage.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(stage))
 with zipfile.ZipFile(archive)as z:
  assert z.testzip() is None
  assert not any(Path(n).name in ('.env','.env.web','sessions.json','expert-kb.json') for n in z.namelist())
 report={'archive':str(archive),'files':len(inventory)+1,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'crc_check':'passed','contains_live_credentials':False}
 (destination/'bundle-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'output/release');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);build(a.out)
