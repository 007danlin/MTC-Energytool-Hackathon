# Склейка нескольких PNG в один ряд для быстрого просмотра: pair.py out.png a.png b.png ...
import sys
from PIL import Image
out, names = sys.argv[1], sys.argv[2:]
ims = [Image.open(n).convert('RGB') for n in names]
gap = 24
W = sum(i.width for i in ims) + gap*(len(ims)+1)
H = max(i.height for i in ims) + gap*2
s = Image.new('RGB', (W, H), '#3a3c44')
x = gap
for i in ims:
    s.paste(i, (x, gap)); x += i.width + gap
s.save(out)
