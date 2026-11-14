# Контактный лист: sheet.py out.png cols thumbW file1 file2 ...
import sys, os
from PIL import Image, ImageDraw, ImageFont
out, cols, tw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
names = sys.argv[4:]
font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), '..', 'fonts', 'Inter.ttf'), 16)
ims = []
for n in names:
    im = Image.open(n).convert('RGB')
    r = tw / im.width
    ims.append((os.path.basename(n), im.resize((tw, int(im.height * r)), Image.LANCZOS)))
th = max(i.height for _, i in ims)
pad = 14
rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (cols * tw + (cols + 1) * pad, rows * (th + 26) + (rows + 1) * pad), '#2f3138')
d = ImageDraw.Draw(sheet)
for i, (n, im) in enumerate(ims):
    x = pad + (i % cols) * (tw + pad); y = pad + (i // cols) * (th + 26 + pad)
    d.text((x, y), n, fill='#fff', font=font)
    sheet.paste(im, (x, y + 24))
sheet.save(out)
