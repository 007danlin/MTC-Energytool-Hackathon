"""Reproducible final defense deck; uses local ReportLab only at authoring time."""
import json
from html import escape
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor,white
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/pdf/EnergyTool-презентация.pdf';OUT.parent.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Arial','/System/Library/Fonts/Supplemental/Arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialB','/System/Library/Fonts/Supplemental/Arial Bold.ttf'))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='ArialB')
W,H=1080,607.5;INK=HexColor('#17181c');MUTED=HexColor('#616772');RED=HexColor('#e40032');BG=HexColor('#f5f6f8');LINE=HexColor('#dfe2e8')
c=canvas.Canvas(str(OUT),pagesize=(W,H));c.setTitle('МТС EnergyTool — ИИ-консультант для сайта');c.setAuthor('Команда EnergyTool')
number=0

def text(s,x,y,w,size=20,color=INK,bold=False):
 s=escape(s).replace('—','-').replace('–','-')
 p=Paragraph(s.replace('\n','<br/>'),ParagraphStyle('p',fontName='ArialB' if bold else 'Arial',fontSize=size,leading=size*1.3,textColor=color,spaceAfter=0))
 pw,ph=p.wrap(w,H);p.drawOn(c,x,H-y-ph);return ph

def rect(x,y,w,h,fill=white):
 c.setFillColor(fill);c.roundRect(x,H-y-h,w,h,14,fill=1,stroke=0)

def start(kicker,title,subtitle=None):
 global number
 number+=1;c.setFillColor(BG);c.rect(0,0,W,H,fill=1,stroke=0)
 text('МТС',42,25,70,25,RED,True);text('EnergyTool',114,30,190,18,INK,True);text(kicker.upper(),680,32,355,12,MUTED)
 text(title,42,91,985,38,INK,True)
 if subtitle:text(subtitle,44,153,970,16,MUTED)
 c.setStrokeColor(LINE);c.line(42,42,W-42,42)
 text('HACK&CHANGE 2026  ·  КЕЙС МТС',42,578,800,10,MUTED)
 text(f'{number:02d}',1003,576,35,12,MUTED)

def end():c.showPage()
def card(x,y,w,h,num,title,body):
 rect(x,y,w,h);text(num,x+22,y+18,w-44,16,RED,True);text(title,x+22,y+49,w-44,24,INK,True);text(body,x+22,y+117,w-44,18)
def screenshot(path,x,y,w,h):
 if path.exists():
  im=ImageReader(str(path));iw,ih=im.getSize();scale=min(w/iw,h/ih);c.drawImage(im,x+(w-iw*scale)/2,H-y-h+(h-ih*scale)/2,iw*scale,ih*scale,mask='auto')
 else: text('Рабочий интерфейс показан в записи demo.mp4 из комплекта.',x,y,w,22)

start('Сдача: ZIP с кодом и PDF','Консультация, после которой\nпонятен следующий шаг')
text('ИИ-консультант для сайта МТС EnergyTool',44,213,960,24,MUTED)
rect(42,286,996,246)
text('Как проверить решение',66,307,900,24,INK,True)
text('1. Откройте README.md в папке project.\n2. Укажите выданные адрес, ключ и модель в .env.web; положите базу в data.\n3. Выполните docker compose up --build -d и откройте 127.0.0.1:8768.',66,353,915,20)
text('Без доступа к модели: запись demo/demo.mp4. Исходники, документация и PDF находятся в этом ZIP.',66,463,915,15,MUTED)
text('Команда: Даниэль · Игорь · Артём · Георгий',44,541,985,13,MUTED)
end()
start('Проблема','От вопроса клиента к понятной задаче','Склад, производство, СНТ: клиент знает свой объект, но не обязан знать энергорынок.')
card(42,207,318,312,'01','Сформулировать','«Счета выросли». Вместо пустой формы - вопрос своими словами и одно полезное уточнение.')
card(380,207,318,312,'02','Разобраться','Ответ с ограничениями из базы. Сведения об объекте, цели и условиях остаются в карточке.')
card(718,207,320,312,'03','Продолжить','Консультация без контакта или добровольная заявка. Менеджеру передаётся контекст разговора.')
end()
start('Сценарий','Живая задача вместо пустого ожидания','Вопрос → уточнение → проверяемый ответ → карточка → сохранённая заявка')
screenshot(ROOT/'reports/release-validation/screens/consultation-desktop.png',42,205,680,335)
text('Во время ответа',756,220,280,23,INK,True)
text('Видно прошедшее время. Можно подготовить следующий черновик и дополнить задачу.',756,268,270,18)
text('После ответа',756,365,280,23,INK,True)
text('Карточка обновляется. Известные факты не нужно вводить заново. Следующий шаг выбирает клиент.',756,410,270,18)
end()
start('Архитектура','Три сервиса. Заменяемая модель.','Ключ API остаётся на сервере; браузер обращается к тому же домену.')
for x,num,title,body in [(42,'01','Веб-интерфейс','Чат, карточка,\nзаявки, специалист'),(380,'02','Go API','История, версии,\nповторы, хранение'),(718,'03','Python + LLM','N2-поиск, контекст,\nпроверка источников')]:card(x,211,320,231,num,title,body)
text('Проверенные знания: редактор → снимок в отдельном томе → поиск при следующем запросе.',44,466,990,20)
text('Демо: локальный JSON, один экземпляр API. Для эксплуатации: БД, авторизация, мониторинг.',44,509,990,16,MUTED)
end()
start('Качество','69,912 — балл замороженного N2','Автоматическая оценка платформы и текущий веб-продукт проверяются отдельно.')
rect(42,211,460,300);text('69,912',68,227,410,72,RED,True);text('Лучший сообщённый результат платформы',70,330,400,23,INK,True);text('Это не процент точности и не оценка локальной модели.',70,413,385,19,MUTED)
text('Почему оставили N2',550,218,450,25,INK,True)
text('BM25 + символьные n-граммы. Документы дополняются условиями и ограничениями.',550,267,440,21)
text('B2 с поиском по смыслу: 45,877 против 55,969 у A2. Дефект многострочного запроса исправлен; влияние на балл не доказано.',550,360,440,20)
text('В веб перенесён поиск N2. Контекст и JSON адаптированы; новый платформенный балл не получен.',550,470,440,17,MUTED)
end()
start('Бизнес-сценарий','Сохранённая заявка становится рабочей карточкой','Один контакт достаточен. Имя и компания не блокируют обращение.')
screenshot(ROOT/'reports/release-validation/screens/applications-desktop.png',42,203,684,337)
text('Очередь и статусы',758,219,280,23,INK,True)
text('Редактирование, история изменений, разбор, принятие или причина отказа. TXT и JSON.',758,268,275,18)
text('Метрики пилота',758,379,275,23,INK,True)
text('Конверсия, принятие, время до заявки и разбора. Демоданные исключены по умолчанию.',758,426,275,18)
end()
start('Человек в контуре','Не знает бот — разбирается специалист','Ответ клиенту и запись для будущего поиска — разные действия.')
screenshot(ROOT/'reports/release-validation/screens/specialist-desktop.png',42,203,680,337)
text('Доставка ответа',756,219,280,23,INK,True)
text('Координатор назначает вопрос. Ответ специалиста подписан в истории; повтор не создаёт дубль.',756,268,275,18)
text('Проверка знаний',756,379,280,23,INK,True)
text('Другой редактор одобряет обобщённый материал. Отзыв убирает его из поиска.',756,426,275,18)
end()
start('Проверка','Совместимость подтверждена контрактом','Фактический API организаторов не вызывался: адрес и ключ для внешнего теста не выданы.')
card(42,211,318,302,'API','Их модель','Адрес, ключ и имя берутся из окружения. Стандартный /chat/completions, без расширений Ollama.')
card(380,211,318,302,'CSV','Их платформа','Неизменённый N2 ZIP запущен с тремя наборами имён переменных. Корректный CSV и ID, SHA сохранён.')
card(718,211,320,302,'WEB','Наш продукт','Python, Go race/vet, сквозной HTTP и браузерные сценарии. Реальные ответы проверены отдельно.')
end()
start('Скорость и границы','Слабое место — задержка локальной модели','Порог 5–7 секунд на нашем Mac не достигнут. Скорость Qwen3.8-27B организаторов не измерена.')
p=ROOT/'reports/release-validation/benchmark-final/summary.json'
if p.exists():
 d=json.loads(p.read_text());stats=[('МЕДИАНА',f"{d['median_seconds']:.1f} с"),('P95',f"{d['p95_seconds']:.1f} с"),('ОШИБКИ',f"{d['technical_errors']} / {d['requests']}")]
else:stats=[('ЗАМЕР','10 запросов'),('МОДЕЛЬ','Локальная'),('ЦЕЛЬ','5–7 с')]
for i,(label,value) in enumerate(stats):
 x=42+i*338;rect(x,215,320,150);text(label,x+24,237,280,14,MUTED);text(value,x+24,276,280,40,RED,True)
text('Последовательная серия, полное время через веб, p95 методом ближайшего ранга. Небольшая смешанная выборка, не промышленный SLA. Все ошибки сохранены в отчёте.',44,395,990,20)
text('После правок: 0 технических ошибок на 5 целевых запросах, медиана 64,5 с. Это другая выборка. Для неизвестной названной интеграции дополнительно включена передача специалисту без догадки о совместимости.',44,482,990,17,MUTED)
end()
start('Внедрение','Пилот, который проверяет пользу','Четыре недели, одно-два направления. Цели и ожидаемый эффект — гипотезы, не обещания.')
card(42,211,318,288,'1 НЕДЕЛЯ','Подготовка','Выбрать направления, критерии принятой заявки и исходную конверсию обычной формы.')
card(380,211,318,288,'2–3 НЕДЕЛИ','Сравнение','Сравнить форму и консультацию. Измерять качество заявки, время разбора и причины отказов.')
card(718,211,320,288,'4 НЕДЕЛЯ','Решение','Проверить эффект. Для внедрения подключить вход, БД, ограничение нагрузки и контракт CRM.')
text('Сейчас: локальный прототип; внешней отправки в CRM нет. Запись демонстрации и порядок проверки входят в комплект сдачи.',44,522,990,16,MUTED)
end()
c.save();print(OUT)
