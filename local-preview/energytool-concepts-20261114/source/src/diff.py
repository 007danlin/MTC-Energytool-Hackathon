# Попиксельное сравнение исходного рендера и проверочной копии артборда: diff.py id...
import sys
from PIL import Image, ImageChops
bad = 0
for i in sys.argv[1:]:
    a = Image.open(f'png1x/{i}.png').convert('RGB'); b = Image.open(f'canvas/check/{i}.png').convert('RGB')
    if a.size != b.size: print(i, 'SIZE', a.size, b.size); bad += 1; continue
    d = ImageChops.difference(a, b).convert('L')
    px = sum(1 for v in d.getdata() if v > 24)
    pct = 100 * px / (a.size[0] * a.size[1])
    if pct > 0.02: bad += 1
    print(f'{i}: {pct:.3f}% differing', d.getbbox() if px else '')
    if pct > 0.02: d.point(lambda v: 255 if v > 24 else 0).save(f'tmp/diff-{i}.png')
print('BAD', bad)
