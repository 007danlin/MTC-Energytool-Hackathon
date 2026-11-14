"""Ten synthetic web requests, sequentially; no score/accuracy claims."""
import argparse,json,math,statistics,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit
CASES=[
 ('warehouse','У нас выросли счета за электроэнергию на складе. С чего начать?'),
 ('warehouse','Счётчики есть. Показания снимаем вручную раз в месяц. Работаем днём. Присоединённая мощность 120 кВт.'),
 ('warehouse','Что можно сделать дальше? Дай краткий план без повторных вопросов.'),
 ('solar','Подойдёт ли солнечная станция для производства, которое работает только ночью?'),
 ('losses','В СНТ показания снимаем вручную, часть домов без счётчиков. Хотим найти потери. С чего начать?'),
 ('unknown','Можно ли интегрировать платформу EnergyTool с системой Demo-Unknown-9000? Подтверждённых сведений о ней у меня нет.'),
 ('house','Частный дом, расходы на электричество 30 000 рублей в год. Хочу уменьшить потребление.'),
 ('meter','Есть счётчики на производстве, но показания переписываем вручную. Как автоматизировать учёт?'),
 ('orem','Завод с присоединённой мощностью 800 кВт хочет рассмотреть оптовый рынок. Какие данные подготовить?'),
 ('warehouse','Хочу обсудить задачу со специалистом. Тестовый контакт для проверки: jury@example.test.'),
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8782');p.add_argument('--out',default='reports/release-validation/benchmark');a=p.parse_args()
 if urlsplit(a.url).hostname not in ('127.0.0.1','localhost'):p.error('Use a local demo stack; cases create sessions.')
 target=Path(a.out);target.mkdir(parents=True,exist_ok=True)
 def call(path,data=None):
  request=Request(a.url+path,data=None if data is None else b'' if data=={} else json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
  with urlopen(request,timeout=270) as r:return json.load(r)
 rows=[];sessions={}
 for i,(scenario,question) in enumerate(CASES):
  if scenario not in sessions:sessions[scenario]=call('/api/v1/sessions',{})['id']
  start=time.monotonic()
  try:result=call('/api/v1/sessions/'+sessions[scenario]+'/messages',{'content':question,'client_request_id':'benchmark-'+str(i)})
  except Exception as error:result={'status':'technical_error','sources':[],'debug':{'error_code':type(error).__name__}}
  row={'case':i+1,'scenario':scenario,'seconds':round(time.monotonic()-start,3),'status':result['status'],'sources':len(result.get('sources',[])),'debug':result.get('debug',{})};rows.append(row)
  (target/('case-%02d.json'%(i+1))).write_text(json.dumps({'question':question,'session_id':sessions[scenario],'result':result},ensure_ascii=False,indent=2))
  (target/'progress.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
  print(json.dumps({k:row[k] for k in ('case','seconds','status','sources')}),flush=True)
 times=sorted(r['seconds'] for r in rows)
 report={'requests':len(rows),'concurrency':1,'method':'wall time, sequential requests through web proxy; nearest-rank p95; mixed scenario sample, not a production SLO','first_request_seconds':rows[0]['seconds'],'median_seconds':statistics.median(times),'p95_seconds':times[math.ceil(.95*len(times))-1],'min_seconds':times[0],'max_seconds':times[-1],'technical_errors':sum(r['status']=='technical_error' for r in rows),'rows':rows,'sessions':sessions}
 (target/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('COMPLETED '+str(target/'summary.json'),flush=True)
if __name__=='__main__':main()
