import os,sys,json,time,threading,subprocess
from pathlib import Path
SESSION=Path(__file__).resolve().parent
ROOT=SESSION.parents[1]/"model-runtime"
os.environ['HF_HOME']=str(ROOT/'hf-cache')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['DO_NOT_TRACK']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
import mlx.core as mx
mx.set_cache_limit(256*1024*1024)
mx.set_memory_limit(23*1024**3)
args=[str(ROOT/'venv/bin/mlx_lm.server'),'--model',str(ROOT/'weights'),'--host','127.0.0.1','--port','18765','--decode-concurrency','1','--prompt-concurrency','1','--prefill-step-size','256','--prompt-cache-size','1','--prompt-cache-bytes','3G','--max-tokens','4096','--chat-template-args','{}']
(SESSION/'server-launch.json').write_text(json.dumps({'pid':os.getpid(),'time':time.time(),'argv':args,'device':mx.device_info(),'cache_limit':256*1024*1024,'memory_guideline':23*1024**3,'kv_dtype':'native (no quantization)','context_limit':'client-enforced; initial32k','warnings':['memory_limit is a guideline, not hard process RAM limit','model is community affine4bit quantization, not unknown provider precision']},indent=2))
print(json.dumps({'event':'launch','pid':os.getpid(),'device':mx.device_info()}),flush=True)
def monitor_memory():
 while True:
  try:
   rss=subprocess.run(['ps','-p',str(os.getpid()),'-o','rss='],capture_output=True,text=True).stdout.strip()
   row={'time':time.time(),'pid':os.getpid(),'rss_bytes':int(rss)*1024,'mlx_active_bytes':mx.get_active_memory(),'mlx_peak_bytes':mx.get_peak_memory(),'mlx_cache_bytes':mx.get_cache_memory()}
   with (SESSION/'server-memory.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  except Exception as e:
   with (SESSION/'server-memory.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'error':str(e)})+'\n')
  time.sleep(2)
threading.Thread(target=monitor_memory,daemon=True).start()
sys.argv=args
from mlx_lm.server import main
main()
