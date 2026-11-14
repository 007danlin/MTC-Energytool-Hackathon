"""Live Go persistence + web proxy + browser contact path; no ML request or model process."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import URLError

ROOT=Path(__file__).resolve().parents[2]

class EmailBrowserAPITests(unittest.TestCase):
    def test_contact_channel_switches_through_real_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=str(Path(tmp)/'api')
            subprocess.run(['go','build','-o',binary,'./cmd/api'],cwd=ROOT/'backend',check=True)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            backend_url='http://127.0.0.1:%d'%port
            env=dict(os.environ,BACKEND_ADDR='127.0.0.1:%d'%port,BACKEND_STORE_PATH=str(Path(tmp)/'sessions.json'),ML_SERVICE_URL='http://127.0.0.1:1')
            process=subprocess.Popen([binary],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            web=None
            try:
                for _ in range(100):
                    try:
                        with urlopen(backend_url+'/health/live',timeout=.1):break
                    except (URLError,OSError):time.sleep(.05)
                else:self.fail('isolated backend failed to start')
                spec=importlib.util.spec_from_file_location('email_web_server',ROOT/'local-preview/energytool-site/serve.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                class Proxy(module.Handler):pass
                Proxy.backend_url=backend_url
                web=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
                threading.Thread(target=web.serve_forever,daemon=True).start()
                env=dict(os.environ,WEB_TEST_URL='http://127.0.0.1:%d'%web.server_port,REAL_CONTACT_API='1')
                subprocess.run(['node','tools/host_tests/test_consultation_email.cjs'],cwd=ROOT,env=env,check=True,timeout=90)
            finally:
                if web:web.shutdown();web.server_close()
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
