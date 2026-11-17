"""Screenshots for the README and docs/, drawn by the app's own graffiti_draw code from its snapshot.
python3 -I shots.py <app dir> <out dir>"""
import builtins, os, sys, types
from PIL import Image, ImageDraw, ImageFont

APP, OUT = (os.path.abspath(p) for p in sys.argv[1:3])
os.makedirs(OUT, exist_ok=True)
builtins.ptr8 = object
mp = types.ModuleType("micropython"); mp.viper = lambda f: f; sys.modules["micropython"] = mp
sys.path.insert(0, APP); os.chdir(APP)
import graffiti_draw as G
import graffiti_chain as C

BLACK, GREEN, GREY, WHITE = 0, 1, 2, 3
BASE = {BLACK: (0, 0, 0), GREEN: (34, 196, 82), GREY: (120, 120, 120), WHITE: (250, 250, 245)}
INKS = list(range(4, 16))
snap = C.Snap()
buf = bytearray(C.BITS)


def image(fb, pal):
    im = Image.new("RGB", (240, 240))
    px = im.load()
    for y in range(240):
        for x in range(240):
            v = fb[y * 120 + x // 2]
            px[x, y] = pal.get(v >> 4 if x % 2 == 0 else v & 15, (0, 0, 0))
    return im


def rgb(c):
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def one(i, badge=None):
    fb = bytearray(120 * 240)
    tid, color = snap.get(i, buf)
    G.scale(fb, buf, G.TAB, INKS[0] | (BLACK << 4))
    im = image(fb, {**BASE, INKS[0]: rgb(color)})
    if badge:
        d = ImageDraw.Draw(im)
        w = 8 * len(badge) + 8
        d.rectangle((0, 228, w - 1, 239), fill=(0, 0, 0))
        d.text((4, 229), badge, fill=BASE[WHITE], font=ImageFont.load_default())
    return im


def wall(page, cursor):
    fb = bytearray(120 * 240)
    pal = dict(BASE)
    for k in range(9):
        i = page * 9 + k
        if i >= snap.count():
            break
        x, y = 12 + (k % 3) * 76, 12 + (k // 3) * 76
        tid, color = snap.get(i, buf)
        pal[INKS[k]] = rgb(color)
        G.thumb(fb, buf, x | (y << 8), INKS[k])
    im = image(fb, pal)
    d = ImageDraw.Draw(im)
    x, y = 12 + (cursor % 3) * 76, 12 + (cursor // 3) * 76
    d.rectangle((x - 4, y - 4, x + 67, y + 67), outline=BASE[GREEN], width=2)
    return im


def big(im, name):
    im.resize((720, 720), Image.NEAREST).save(os.path.join(OUT, name))


big(wall(0, 1), "wall-p0.png")
big(wall(2, 4), "wall-p2.png")
for i in (0, 1, 4, 8, 13, 25, 40):
    big(one(i), "one-%d.png" % i)
big(one(4, "#4 paused"), "show-4.png")

# the whole collection: 13 x 8 thumbnails
cols, rows, cell, gap = 13, 8, 64, 8
sheet = Image.new("RGB", (gap + cols * (cell + gap), gap + rows * (cell + gap)), (0, 0, 0))
for i in range(snap.count()):
    fb = bytearray(120 * 240)
    tid, color = snap.get(i, buf)
    G.thumb(fb, buf, 0, INKS[0])
    t = image(fb, {INKS[0]: rgb(color)}).crop((0, 0, 64, 64))
    sheet.paste(t, (gap + (i % cols) * (cell + gap), gap + (i // cols) * (cell + gap)))
sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(os.path.join(OUT, "collection.png"))
print(sorted(os.listdir(OUT)))
