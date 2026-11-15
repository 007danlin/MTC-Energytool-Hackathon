"""Revise the supplied PDF in place geometrically, preserving its MTS artwork.

Authoring dependency: PyMuPDF 2.1, Pillow; not an application dependency.
Requires the original PDF, full MTS fonts and a saved synthetic manager screenshot.
"""
import argparse, io
from pathlib import Path
import pymupdf as fitz
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
INK=(.09,.09,.11); RED=(1,0,.20); MUTED=(.32,.33,.38); WHITE=(1,1,1)

def revise(font_dir,manager_image,out):
 doc=fitz.open(ROOT/'deliverables/2026-11-15/Energytool_presentation_MTS_style.pdf')
 fonts={name:next(font_dir.rglob(file)).read_bytes() for name,file in
        [('Heading','MTSWide-Medium.ttf'),('Body','MTSText-Regular.ttf')]}
 edits={i:[] for i in range(10)}
 def box(i,rect,text,size=22,font='Body',color=INK,clear=True):
  edits[i].append((fitz.Rect(rect),text,size,font,color,clear))
 titles={1:'Клиент знает свой объект, а не энергорынок',
         2:'Консультация с опорой на базу знаний',
         3:'Реальный диалог и возвращение после паузы',
         4:'Три сервиса. Заменяемая модель',
         5:'N2: 69,912 — лучший public-результат нашей команды',
         6:'Менеджер получает контакт и контекст задачи',
         7:'Ответ специалиста сохраняется в истории',
         8:'Задержку измерили. Продолжение проверили',
         9:'Пилот: измерить пользу для клиента и бизнеса'}
 for i,title in titles.items():
  box(i,(56,27,1318,123),title,36 if i==5 else 38,'Heading')
  box(i,(56,766,1100,794),'MISISion possible · Hack&Change 2026 · кейс МТС',15,color=MUTED)

 # Cover: keep the original type, logo and decorative layout.
 box(0,(83,239,900,274),'Комплект для сдачи',21,'Heading')
 box(0,(108,632,478,675),'project/README.md',20,'Heading')
 box(0,(512,632,889,680),'.env.web: адрес, ключ, модель',18,'Heading')
 box(0,(915,605,1283,675),'03  Из папки project\ndocker compose up --build -d',18,'Heading')
 box(0,(83,691,1260,751),'ZIP: код, документы, PDF и демо. Чат: http://127.0.0.1:8768/consultation.html\nБез API модели: demo/demo.mp4. Адрес чата локальный.',19,color=MUTED)
 box(1,(56,740,1280,765),'Источник: кейс МТС, стр. 4–5. Около 400 тыс. — оценка аудитории из кейса.',17,color=MUTED,clear=False)

 # Consultation stages: avoid guarantees and make evidence boundaries explicit.
 box(2,(351,331,559,523),'Уточняет задачу и недостающие сведения об объекте.',22)
 box(2,(620,291,836,328),'Ответ по базе',23,'Heading')
 box(2,(620,331,836,535),'Сведения о продуктах — из базы. Факты клиента — из диалога.',22)
 box(2,(888,291,1100,328),'Нет данных',23,'Heading')
 box(2,(888,331,1100,535),'Сообщает, что подтверждения нет. Предлагает специалиста.',22)
 box(2,(1157,331,1364,535),'Клиент проверяет контакт и резюме перед сохранением.',22,color=WHITE)
 box(2,(80,609,407,643),'Ответ с опорой на источники',19)
 box(2,(80,663,423,700),'Цитата не доказывает каждый вывод',17)
 box(2,(56,725,1320,754),'Не обещаем отсутствие ошибок: проверяем цитаты и блокируем найденные классы неподтверждённых выводов.',18,color=MUTED,clear=False)

 # A real conversation, shortened with explicit attribution, replaces a tiny full-screen capture.
 doc[3].delete_image(29)
 box(3,(83,157,890,191),'Кафе: фрагменты живого диалога',21,'Heading')
 box(3,(95,218,860,251),'КЛИЕНТ',17,'Heading',RED,False)
 box(3,(95,254,860,329),'«Счета выросли после установки второй холодильной витрины. Какие первые действия помогут разобраться?»',25,clear=False)
 box(3,(95,345,860,378),'КОНСУЛЬТАНТ',17,'Heading',RED,False)
 box(3,(95,382,860,477),'«Сначала сравните два периода: до и после установки второй витрины. Проверьте три показателя: объём потребления, среднюю цену за киловатт-час и плату за мощность».',24,clear=False)
 box(3,(95,478,860,511),'КЛИЕНТ',17,'Heading',RED,False)
 box(3,(95,514,860,582),'«Модель нашего существующего электросчётчика мне неизвестна. Можно ли подключить его без замены?»',24,clear=False)
 box(3,(95,586,860,619),'КОНСУЛЬТАНТ',17,'Heading',RED,False)
 box(3,(95,622,860,723),'«Совместимость существующих счётчиков пока не подтверждена. Это не означает, что их обязательно нужно менять». ',23,clear=False)
 box(3,(968,157,1355,195),'Во время ожидания',21,'Heading')
 box(3,(968,211,1355,321),'Видны время и состояние. Можно набрать следующий вопрос. После 20 с — заявка оператору.',21)
 box(3,(968,359,1355,397),'Возврат без потери',21,'Heading')
 box(3,(968,412,1355,523),'Прерывание → выход на сайт → возврат. Беседа и черновик сохраняются. «Новый диалог» — чистый контекст.',21)
 box(3,(968,562,1355,600),'Проверено вживую',21,'Heading',INK)
 box(3,(968,614,1355,729),'Дважды пройден путь до заявки на живой модели. Ещё 27 действий с API: формы, история, мобильные окна.',21, color=INK)
 box(3,(83,740,900,765),'Тестовый сценарий 15.11.2026 · Фрагменты сокращены · docs/live-user-audit.md',16,color=MUTED,clear=False)

 box(4,(83,540,472,699),'Релевантные разделы, документы продукта и правила — в пределах лимита контекста. Фильтр применимости исключает требования другого продукта.',21)
 box(4,(519,540,918,699),'Сервер проверяет происхождение цитат. Знания специалиста попадают в поиск после одобрения редактора.',21)
 box(4,(956,540,1358,699),'Ключ API остаётся на сервере. Запуск — одной Docker-командой. Демо: JSON, один экземпляр API; промышленная авторизация не реализована.',21)

 box(5,(83,607,865,677),'Балл платформы, не процент точности и не место среди команд.\nB2 — поиск по смыслу. N2 выбран по нашим платформенным результатам.',18)
 box(5,(930,281,1353,506),'В веб адаптирован поиск N2. Его конкурсный балл не переносится на веб автоматически.\n\nПобедивший ML-архив сохранён без изменений.',22)
 box(5,(930,566,1353,604),'Авторская проверка',21,'Heading',INK)
 box(5,(930,620,1353,725),'123 вопроса и 154 обязательных факта. Это наш набор, не закрытые тесты организаторов.',22,color=INK)
 box(5,(56,740,1330,765),'Источник: сохранённые результаты платформы; N2 — 12.11.2026. Итог private-проверки здесь не заявляется.',17,color=MUTED,clear=False)

 # Manager and specialist screenshots: crop the actual evidence, never recreate their UI.
 original_images={6:doc.extract_image(45)['image'],7:doc.extract_image(50)['image']}
 doc[6].delete_image(45);doc[7].delete_image(50)
 screenshots=[(6,Image.open(manager_image).crop((10,735,985,1340)),(85,228,890,728)),
              (7,Image.open(io.BytesIO(original_images[7])).crop((418,194,1415,747)),(85,217,890,665))]
 for i,im,rect in screenshots:
  b=io.BytesIO();im.save(b,format='PNG');doc[i].insert_image(rect,stream=b.getvalue(),keep_proportion=True)
 box(6,(83,157,899,197),'Тестовая заявка №985293: склад, два арендатора',20,'Heading')
 box(6,(968,210,1355,310),'Взять в работу, принять, отклонить с причиной. Изменения сохраняются; карточку можно выгрузить.',21)
 box(6,(968,397,1355,520),'Контакт, сведения клиента и вопросы для уточнения. Статусы отделяют подтверждённое от предположений.',21)
 box(6,(968,562,1355,602),'Для будущего пилота',20,'Heading')
 box(6,(968,614,1355,729),'Есть события для расчёта конверсии, принятия и времени разбора. Бизнес-эффект пока не измерен.',21)
 box(6,(83,740,905,765),'Клиент проверяет заявку перед сохранением. Достаточно одного контакта.',17,color=MUTED,clear=False)
 box(7,(968,212,1355,320),'Ответ с подписью специалиста сохраняется в истории, в том числе при закрытом диалоге.',21)
 box(7,(968,415,1355,523),'Другой редактор проверяет знание перед публикацией. Только затем оно попадает в поиск.',21)
 box(7,(968,562,1355,602),'Дополнение к кейсу',21,'Heading',INK)
 box(7,(968,615,1355,730),'Кабинет и пополнение базы не обязательны по Q&A. Они поддерживают разбор вопросов без подтверждённого ответа.',21,color=INK)
 box(7,(83,688,890,746),'Крупный фрагмент технической проверки публикации.\nДля эксплуатации нужны авторизация и контроль доступа.',19,color=MUTED,clear=False)

 # Measured speed: preserve both original series and their different denominators.
 box(8,(983,157,1357,197),'Технические отказы',21,'Heading')
 box(8,(83,306,462,354),'10 запросов через полный веб-стек',17)
 box(8,(983,306,1355,354),'Не оценка всех содержательных ошибок',17)
 box(8,(83,401,468,445),'Отдельная перепроверка',20,'Heading')
 box(8,(83,463,468,705),'5 целевых запросов после правок: 0 технических ошибок.\nМедиана: 64,5 с.\n\nДругой набор: сравнивать скорость с серией из 10 нельзя.',22)
 box(8,(533,401,917,445),'Что пока ограничено',20,'Heading')
 box(8,(533,463,917,705),'Ориентир 5–7 с не достигнут.\n\nДемо без входа: JSON-хранилище и один API. CRM и реальная отправка писем не подключены.',22)
 box(8,(983,401,1357,445),'Что уже проверено',20,'Heading')
 box(8,(983,463,1357,705),'Возврат после прерывания и заявка во время ожидания.\n\n132 unit-теста проверяют код и регрессии, а не правильность всех ответов модели.',22)
 box(8,(56,740,1340,765),'Локальная Qwen3-VL-30B-A3B, 14.11.2026; не модель организаторов. Источник: docs/release-readiness.md',17,color=MUTED,clear=False)

 box(9,(983,450,1355,490),'Польза для клиента',21,'Heading')
 box(9,(983,510,1355,700),'Клиенту — понятный следующий шаг. Менеджеру — контекст задачи.\n\nРост конверсии и экономию времени ещё предстоит проверить пилотом.',21)
 box(9,(83,510,918,547),'Измеряем по событиям; цели пилота — гипотезы:',21)
 box(9,(56,690,1340,752),'Команда: Даниэль — ИИ и сабмиты; Артём — поиск, проверочный набор и бизнес-логика;\nИгорь — сервер и интеграция; Георгий — сайт и чат.',18,color=MUTED,clear=False)

 for i,page in enumerate(doc):
  for rect,text,size,font,color,clear in edits[i]:
   if clear:page.add_redact_annot(rect,fill=False,cross_out=False)
  page.apply_redactions(images=0,graphics=0,text=0)
  for name,buf in fonts.items():page.insert_font(fontname=name,fontbuffer=buf)
  for rect,text,size,font,color,clear in edits[i]:
   fontobj=fitz.Font(fontbuffer=fonts[font])
   missing={c for c in text if not c.isspace() and not fontobj.has_glyph(ord(c))}
   if missing:raise ValueError((i+1,'missing glyphs',missing))
   # Text is wrapped by the PDF engine; failure is a hard error, never clipping.
   for delta in (0,.5,1,1.5,2):
    spare=page.insert_textbox(rect,text,fontname=font,fontsize=size-delta,color=color,lineheight=1.18)
    if spare>=0:break
   if spare<0:raise ValueError((i+1,rect,'overflow',spare,text))
 doc.set_metadata({**doc.metadata,'title':'МТС EnergyTool — презентация для сдачи','author':'MISISion possible','subject':'Редакция от 15 ноября 2026; N2, живой сценарий, ограничения и пилот'})
 out.parent.mkdir(parents=True,exist_ok=True)
 doc.subset_fonts();doc.save(out,garbage=4,deflate=True)
 print(out)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--fonts',type=Path,required=True);p.add_argument('--manager-image',type=Path,default=ROOT/'deliverables/2026-11-15/assets/manager-demo.png')
 p.add_argument('--out',type=Path,default=ROOT/'deliverables/2026-11-15/Energytool_presentation_MTS_style_final.pdf')
 a=p.parse_args();revise(a.fonts,a.manager_image,a.out)
