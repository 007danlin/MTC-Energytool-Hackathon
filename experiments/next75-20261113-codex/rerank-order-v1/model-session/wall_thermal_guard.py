import os,time,json,signal,subprocess,ctypes,datetime,re
from pathlib import Path
SESSION=Path(__file__).resolve().parent
BASE=SESSION.parent
manifest=json.loads((BASE/'live/manifest.json').read_text())
START=float(manifest['started_unix']);DEADLINE=START+3600.0
assert float(manifest['wall_budget_seconds'])==3600.0
RUNNER_PID=16509
runtime=json.loads((SESSION/'session-manifest.json').read_text())
SERVER_PID=runtime['server_pid'];SUPERVISOR_PID=runtime['supervisor_pid']
first=json.loads((BASE/'live/01-hold01-n2/http/00001.metadata.json').read_text())
assert first['state']=='finished'
FIRST_FINISHED=(BASE/'live/01-hold01-n2/http/00001.metadata.json').stat().st_mtime
ctypes.CDLL('/System/Library/Frameworks/Foundation.framework/Foundation')
objc=ctypes.CDLL('/usr/lib/libobjc.A.dylib')
objc.objc_getClass.argtypes=[ctypes.c_char_p];objc.objc_getClass.restype=ctypes.c_void_p
objc.sel_registerName.argtypes=[ctypes.c_char_p];objc.sel_registerName.restype=ctypes.c_void_p
send=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)(('objc_msgSend',objc))
send_int=ctypes.CFUNCTYPE(ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p)(('objc_msgSend',objc))
process_info=send(objc.objc_getClass(b'NSProcessInfo'),objc.sel_registerName(b'processInfo'))
thermal_selector=objc.sel_registerName(b'thermalState')

def save(name,obj):
    (SESSION/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))

def identity(pid):
    out={}
    for field in ('args','comm','lstart','stat'):
        p=subprocess.run(['ps','-p',str(pid),'-o',field+'='],capture_output=True,text=True,timeout=5)
        out[field]=p.stdout.strip()
    out['pid']=pid;out['present']=bool(out['comm']) and not out['stat'].startswith('Z')
    return out

identities={str(pid):identity(pid) for pid in (RUNNER_PID,SUPERVISOR_PID,SERVER_PID)}
runner=identities[str(RUNNER_PID)]
assert runner['present'] and 'python' in runner['comm'].lower()
assert 'experiments/next75-20261113-codex/rerank-order-v1/run_pairs.py' in runner['args']
assert '--budget-seconds 3600' in runner['args']
for pid,filename in [(SUPERVISOR_PID,'supervise_model.py'),(SERVER_PID,'launch_server.py')]:
    found=identities[str(pid)]
    assert found['present'] and str(SESSION/filename) in found['args']

save('wall-thermal-guard-manifest.json',{'created_unix':time.time(),'guard_pid':os.getpid(),'series_started_unix':START,'fixed_wall_deadline_unix':DEADLINE,'wall_budget_seconds':3600,'identities':identities,'first_http_finished_mtime_unix':FIRST_FINISHED,'thermal_stop_values':[2,3],'thermal_labels':{'2':'serious','3':'critical'},'stop_sequence':'verify runner argv/lstart, SIGINT runner, allow20s cleanup, SIGTERM own supervisor; direct own server SIGTERM fallback only if verified','poll_seconds':5,'model_requests_sent':0,'clock_caveat':'Guard cannot execute during host sleep; it checks fixed real-wall deadline immediately on next wake.'})
print(json.dumps({'event':'wall_thermal_guard_started','guard_pid':os.getpid(),'runner_pid':RUNNER_PID,'deadline_unix':DEADLINE}),flush=True)

def same(pid):
    current=identity(pid);old=identities[str(pid)]
    return current,current['present'] and current['args']==old['args'] and current['lstart']==old['lstart']

def wait_exit(pid,seconds):
    until=time.time()+seconds
    while time.time()<until:
        if not identity(pid)['present']:return True
        time.sleep(.5)
    return not identity(pid)['present']

def new_emergency_sleep_events():
    p=subprocess.run(['pmset','-g','log'],capture_output=True,text=True,timeout=30)
    events=[]
    for line in p.stdout.splitlines():
        if 'Entering Sleep' not in line or 'Thermal Emergency Sleep' not in line:continue
        try:ts=datetime.datetime.strptime(line[:25],'%Y-%m-%d %H:%M:%S %z').timestamp()
        except ValueError:continue
        if ts>FIRST_FINISHED:events.append({'time_unix':ts,'line':line})
    return events

previous_wall=time.time();previous_mono=time.monotonic();reason=None;trigger=None
while True:
    now=time.time();mono=time.monotonic();current,valid=same(RUNNER_PID)
    if not current['present']:
        save('wall-thermal-guard-exit.json',{'time_unix':now,'reason':'runner_already_finished','runner_identity':current,'signals_sent':[]});print(json.dumps({'event':'guard_exit_runner_finished'}),flush=True);raise SystemExit(0)
    if not valid:
        save('wall-thermal-guard-exit.json',{'time_unix':now,'reason':'runner_identity_changed_no_signal','runner_identity':current,'signals_sent':[]});raise SystemExit(3)
    state=send_int(process_info,thermal_selector)
    excess=(now-previous_wall)-(mono-previous_mono)
    row={'time_unix':now,'monotonic':mono,'continuous_raw':time.clock_gettime(time.CLOCK_MONOTONIC_RAW),'seconds_to_fixed_wall_deadline':DEADLINE-now,'thermal_state':state,'thermal_label':{0:'nominal',1:'fair',2:'serious',3:'critical'}.get(state,'unknown'),'wall_minus_uptime_step':excess}
    with (SESSION/'wall-thermal-guard-observations.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    if now>=DEADLINE:reason='original_3600_second_real_wall_budget_exhausted';trigger=row;break
    if state in (2,3):reason='current_thermal_'+row['thermal_label'];trigger=row;break
    if excess>5:
        events=new_emergency_sleep_events()
        with (SESSION/'wake-checks.jsonl').open('a') as f:f.write(json.dumps({'time_unix':now,'wall_minus_uptime_step':excess,'new_emergency_events':events})+'\n')
        if events:reason='new_Thermal_Emergency_Sleep_after_first_HTTP';trigger={'clock':row,'events':events};break
    previous_wall=now;previous_mono=mono;time.sleep(5)

record={'time_unix':time.time(),'reason':reason,'trigger':trigger,'fixed_wall_deadline_unix':DEADLINE,'series_started_unix':START,'signals':[],'other_user_processes_touched':False}
current,valid=same(RUNNER_PID);record['runner_pre_signal_identity']=current
if not valid:
    record['aborted']='runner_identity_changed';save('wall-thermal-intervention.json',record);raise SystemExit(3)
os.kill(RUNNER_PID,signal.SIGINT);record['signals'].append({'time_unix':time.time(),'pid':RUNNER_PID,'signal':'SIGINT','argv_verified':True,'start_time_verified':True});save('wall-thermal-intervention.json',record)
print(json.dumps({'event':'intervention_runner_SIGINT','reason':reason,'pid':RUNNER_PID}),flush=True)
record['runner_exited_within20s']=wait_exit(RUNNER_PID,20)
current,valid=same(SUPERVISOR_PID);record['supervisor_pre_signal_identity']=current
if valid:
    os.kill(SUPERVISOR_PID,signal.SIGTERM);record['signals'].append({'time_unix':time.time(),'pid':SUPERVISOR_PID,'signal':'SIGTERM','argv_verified':True,'start_time_verified':True});record['supervisor_exited_within20s']=wait_exit(SUPERVISOR_PID,20)
current,valid=same(SERVER_PID);record['server_pre_fallback_identity']=current
if valid:
    os.kill(SERVER_PID,signal.SIGTERM);record['signals'].append({'time_unix':time.time(),'pid':SERVER_PID,'signal':'SIGTERM','argv_verified':True,'start_time_verified':True,'fallback':True});record['server_exited_within15s']=wait_exit(SERVER_PID,15)
record['final_identities']={str(pid):identity(pid) for pid in (RUNNER_PID,SUPERVISOR_PID,SERVER_PID)};record['finished_unix']=time.time();save('wall-thermal-intervention.json',record)
print(json.dumps({'event':'wall_thermal_intervention_complete','reason':reason,'finished_unix':record['finished_unix']}),flush=True)
