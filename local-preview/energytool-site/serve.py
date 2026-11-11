from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import urllib.parse,json
P=Path(__file__).resolve().parent/'www'
class Handler(SimpleHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def __init__(self,*args,**kw):super().__init__(*args,directory=str(P),**kw)
 def end_headers(self):
  self.send_header('Content-Security-Policy',"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://api-maps.yandex.ru https://yastatic.net; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https://*.yandex.ru https://*.yandex.net; frame-src 'none'; form-action 'self'");super().end_headers()
 def api(self):
  b=json.dumps({'error':'local_preview','message':'Это локальная копия. Отправка заявок и авторизация МТС не подключены.'},ensure_ascii=False).encode();self.send_response(503);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):self.api()
 def do_GET(self):
  path=urllib.parse.urlsplit(self.path).path
  if path=='/api/shop':self.path='/public-shop.json';return super().do_GET()
  if path.startswith('/api/'):return self.api()
  candidate=P/path.lstrip('/')
  if not candidate.exists() and '.' not in Path(path).name:self.path='/index.html'
  super().do_GET()
ThreadingHTTPServer.request_queue_size=128
print('Energytool local preview: http://127.0.0.1:8767',flush=True)
ThreadingHTTPServer(('127.0.0.1',8767),Handler).serve_forever()
