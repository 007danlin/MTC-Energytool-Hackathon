"""Build the final project bundle, excluding live state, credentials and research exports."""
import argparse,hashlib,json,shutil,zipfile,subprocess
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
 shutil.copy2(ROOT/'deliverables/2026-11-15/Energytool_presentation_MTS_style.pdf',stage/'EnergyTool-презентация.pdf')
 (stage/'ml-submit').mkdir();shutil.copy2(ROOT/'artifacts/mts-energytool-n2-docs.zip',stage/'ml-submit/N2-победивший-сабмит.zip')
 if (ROOT/'deliverables/2026-11-14/demo.mp4').exists():
  (stage/'demo').mkdir();shutil.copy2(ROOT/'deliverables/2026-11-14/demo.mp4',stage/'demo/demo.mp4')
  shutil.copy2(ROOT/'deliverables/2026-11-14/demo-README.txt',stage/'demo/README.txt')
 (stage/'SOURCE_REVISION.txt').write_text(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()+'\n')
 (stage/'НАЧНИТЕ-ЗДЕСЬ.txt').write_text('''Финальная сдача EnergyTool: код, документы, PDF и запись демонстрации.

1. Прочитайте презентацию EnergyTool-презентация.pdf.
2. Исходники и инструкция запуска: project/README.md.
3. В project создайте .env.web из .env.web.example и впишите ВЫДАННЫЕ адрес, ключ и идентификатор модели. База организаторов приложена для закрытой проверки в project/data. Не публикуйте комплект открыто.
4. Из project выполните: docker compose up --build -d
5. Откройте http://127.0.0.1:8768/consultation.html
6. Без API модели посмотрите demo/demo.mp4. Запись использует реальную локальную модель, тестовый контакт и отдельное хранилище.

ml-submit/N2-победивший-сабмит.zip — неизменённый архив автоматического этапа. Не загружайте весь этот комплект вместо ML-сабмита: это разные этапы.

Фактические проверки и ограничения: project/docs/release-readiness.md.
Ключей и реальной пользовательской истории в комплекте нет. По решению владельца сдаётся самодостаточный ZIP; доступ к приватному GitHub не открывался. Формулировка формы о доступе жюри отмечена в project/docs/final-submission-audit.md.
''',encoding='utf-8')
 (stage/'README.md').write_text('''# МТС EnergyTool — финальный проект для экспертной оценки

Секция: Трек AI от МТС. Первый тур. Формат: ZIP с исходниками, документацией и PDF.
Это не сабмит для автоматической проверки на private-выборке.

1. Презентация: `EnergyTool-презентация.pdf` — исходный вариант Артёма без изменений.
2. Код и полная инструкция: `project/README.md`. Перейдите в `project`.
3. Скопируйте `.env.web.example` в `.env.web` и задайте адрес, ключ и имя доступной модели. При финальном ручном запуске они не появляются автоматически. База уже приложена в `project/data/knowledge-base.zip`.
4. Запуск: `docker compose up --build -d` из папки `project`.
5. Чат: http://127.0.0.1:8768/consultation.html . Без API: запись `demo/demo.mp4`.

Docker Desktop / Docker Engine с Compose и доступ к реестру образов необходимы для сборки. Node.js и PDF-библиотеки для запуска продукта не нужны. Все рабочие данные будут созданы в новых Docker-томах.

Проверка комплекта и ограничения: `project/docs/final-submission-audit.md`.
`ml-submit/N2-победивший-сабмит.zip` — только архив отдельного автоматического этапа, сохранён для воспроизводимости. Для этой кнопки загружайте весь финальный ZIP.

Комплект включает закрытую базу организаторов: предназначен для закрытой сдачи на платформе, не для публичной публикации. Репозиторий для запуска не нужен.
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
 from validate_release_bundle import validate
 report={'archive':str(archive),**validate(archive)}
 (destination/'bundle-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'output/release');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);build(a.out)
