import json,os,time,sys,signal,subprocess,socket,urllib.request,urllib.error,hashlib
from pathlib import Path
SESSION=Path(__file__).resolve().parent
ROOT=SESSION.parents[1]/'model-runtime'
stop_requested=None

def write_json(name,obj):
    (SESSION/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))

def endpoints():
    results={};resident=[];uncertain=[]
    for port in (11434,11435):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ps',timeout=2) as response:data=json.load(response)
            models=data.get('models')
            if not isinstance(models,list):raise ValueError('Missing models list')
            results[str(port)]=data
            resident.extend({'port':port,'name':m.get('name'),'size_vram':m.get('size_vram')} for m in models)
        except Exception as exc:
            reason=getattr(exc,'reason',None)
            refused=isinstance(reason,ConnectionRefusedError) or getattr(reason,'errno',None)==61
            results[str(port)]={'error':type(exc).__name__+': '+str(exc),'connection_refused':refused}
            if not refused:uncertain.append(port)
    return results,resident,uncertain

def foreign_runners():
    raw=subprocess.run(['ps','-axo','pid,comm'],capture_output=True,text=True,timeout=5).stdout
    rows=[]
    for line in raw.splitlines():
        if 'llama-server' in line.lower():rows.append(line.strip())
    return rows

def system_snapshot():
    level=subprocess.run(['sysctl','-n','kern.memorystatus_vm_pressure_level'],capture_output=True,text=True,timeout=5).stdout.strip()
    swap=subprocess.run(['sysctl','vm.swapusage'],capture_output=True,text=True,timeout=5).stdout.strip()
    vm=subprocess.run(['vm_stat'],capture_output=True,text=True,timeout=5).stdout
    return {'pressure_level':level,'swap':swap,'vm_stat':vm}

def port_open():
    with socket.socket() as s:
        s.settimeout(.5)
        return s.connect_ex(('127.0.0.1',18765))==0

def signal_stop(signum,frame):
    global stop_requested
    stop_requested='supervisor_signal_'+str(signum)

signal.signal(signal.SIGTERM,signal_stop)
signal.signal(signal.SIGINT,signal_stop)
start=time.time();eps,resident,uncertain=endpoints();foreign=foreign_runners();system=system_snapshot()
preflight={'time_unix':start,'endpoints':eps,'resident_models':resident,'foreign_llama_processes':foreign,'uncertain_endpoints':uncertain,'system':system,'port_18765_busy':port_open()}
write_json('preflight.json',preflight)
if resident or foreign or uncertain or system['pressure_level']!='1' or preflight['port_18765_busy']:
    write_json('preflight-blocked.json',preflight);print(json.dumps({'event':'preflight_blocked','preflight':preflight}),flush=True);raise SystemExit(2)
old_manifest=json.loads((ROOT/'weights-manifest.json').read_text())
for row in old_manifest['files']:
    assert (ROOT/'weights'/row['file']).stat().st_size==row['bytes'],row['file']
runtime=json.loads((ROOT/'runtime-manifest.json').read_text())
for row in runtime['modules']:
    assert hashlib.sha256(Path(row['file']).read_bytes()).hexdigest()==row['sha256'],row['module']
launch=[str(ROOT/'venv/bin/python'),'-u',str(SESSION/'launch_server.py')]
log=(SESSION/'server.log').open('w')
child=subprocess.Popen(launch,stdout=log,stderr=subprocess.STDOUT,cwd='/private/tmp')
manifest={'created_unix':time.time(),'supervisor_pid':os.getpid(),'server_pid':child.pid,'launch_command':launch,'weights_repo':old_manifest['repo'],'weights_revision':old_manifest['revision'],'weights_manifest_file':str(ROOT/'weights-manifest.json'),'weight_sizes_checked':True,'weight_hashes_reused_from_verified_download':True,'runtime_modules_rehashed_and_match':True,'runtime':runtime,'preflight_file':'preflight.json','model_id':str(ROOT/'weights'),'base_url':'http://127.0.0.1:18765/v1','configuration':'same launch parameters as first session; native default thinking; no business or smoke requests sent by supervisor','budget_seconds':3600,'budget_owner':'root pair driver','guards':{'foreign_resident_model':'terminate only our server immediately upon observation','foreign_llama_server_process':'terminate only our server immediately upon observation','system_critical':'terminate only our server after2 consecutive pressure4 observations15seconds apart','endpoint_uncertainty':'stop our server if a previously responding local endpoint becomes unreadable except connection refused'},'poll_seconds':5,'pressure_sample_seconds':15}
write_json('session-manifest.json',manifest)
print(json.dumps({'event':'server_started','pid':child.pid,'supervisor_pid':os.getpid()}),flush=True)
next_pressure=0;critical_streak=0;last_level=None;last_system=system;ready=False;reason=None;trigger=None
try:
    while child.poll() is None:
        now=time.time()
        if stop_requested:
            reason=stop_requested;trigger={'time_unix':now};break
        eps,resident,uncertain=endpoints();foreign=foreign_runners()
        sampled=now>=next_pressure
        if sampled:
            last_system=system_snapshot();next_pressure=now+15
            critical_streak=critical_streak+1 if last_system['pressure_level']=='4' else 0
            level=last_system['pressure_level']
            if level!=last_level and level in ('2','4'):print(json.dumps({'event':'pressure_change','level':level,'time_unix':now}),flush=True)
            last_level=level
        row={'time_unix':now,'server_pid':child.pid,'resident_models':resident,'foreign_llama_processes':foreign,'endpoint_uncertainty':uncertain,'endpoints':eps,'pressure_sampled':sampled,'critical_streak':critical_streak,'system':last_system}
        with (SESSION/'watchdog-observations.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        if resident or foreign:
            reason='foreign_model_or_llama_runner_detected';trigger=row;break
        if uncertain:
            reason='local_model_endpoint_state_uncertain';trigger=row;break
        if critical_streak>=2:
            reason='two_consecutive_system_CRITICAL_samples';trigger=row;break
        if not ready and port_open() and (SESSION/'server-memory.jsonl').exists():
            lines=(SESSION/'server-memory.jsonl').read_text().splitlines()
            if lines:
                memory=json.loads(lines[-1])
                if memory.get('mlx_active_bytes',0)>14*2**30:
                    ready=True
                    write_json('ready.json',{'time_unix':now,'server_pid':child.pid,'supervisor_pid':os.getpid(),'memory':memory,'business_requests_sent':0,'smoke_requests_sent':0})
                    print(json.dumps({'event':'ready','server_pid':child.pid,'base_url':manifest['base_url'],'model_id':manifest['model_id']}),flush=True)
        time.sleep(5)
finally:
    if child.poll() is None:
        reason=reason or 'supervisor_finally_cleanup'
        action={'time_unix':time.time(),'reason':reason,'trigger':trigger,'server_pid':child.pid,'server_command':launch,'actions':['SIGTERM own child'],'other_processes_touched':False}
        child.terminate()
        try:child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill();child.wait(timeout=10);action['actions'].append('SIGKILL own child after15s')
        action['exit_code']=child.returncode;action['finished_unix']=time.time();write_json('watchdog-stop.json',action)
        print(json.dumps({'event':'own_server_stopped','reason':reason,'server_pid':child.pid,'exit_code':child.returncode}),flush=True)
    else:
        write_json('server-exit.json',{'time_unix':time.time(),'server_pid':child.pid,'exit_code':child.returncode,'reason':'server_exited_or_external_owner_stopped_it'})
    log.close()
