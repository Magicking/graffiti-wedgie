"""Host test for the Graffiti wedgie app: fake firmware modules, real app code.

python3 -I test_graffiti.py <app dir> <chain fixtures dir> <out dir>
"""
import builtins
import os
import sys
import types
import zlib
import struct

APP, FIX, OUT = (os.path.abspath(p) for p in sys.argv[1:4])
os.makedirs(OUT, exist_ok=True)

# ---- fake firmware
builtins.ptr8 = object
mp = types.ModuleType("micropython")
mp.viper = lambda f: f
sys.modules["micropython"] = mp

PAL = [(0, 0, 0)] * 16
BASE = [(255, 255, 255), (20, 20, 20), (120, 120, 120), (34, 196, 82), (20, 120, 50), (180, 180, 180),
        (220, 50, 50), (0, 0, 0), (255, 220, 0), (40, 100, 230), (60, 60, 60), (90, 90, 90), (150, 150, 150),
        (200, 200, 200), (230, 230, 230), (10, 10, 10)]


class LCD:
    width = height = 240

    def __init__(self):
        self.buffer = bytearray(120 * 240)
        self.shows = 0

    def _px(self, x, y, c):
        if 0 <= x < 240 and 0 <= y < 240:
            i = y * 120 + x // 2
            v = self.buffer[i]
            self.buffer[i] = (v & 0x0F) | (c << 4) if x % 2 == 0 else (v & 0xF0) | c

    def fill(self, c):
        PAL[:] = BASE
        self.buffer[:] = bytes([(c << 4) | c]) * len(self.buffer)

    def fill_rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._px(xx, yy, c)

    def rect(self, x, y, w, h, c):
        for xx in range(x, x + w):
            self._px(xx, y, c); self._px(xx, y + h - 1, c)
        for yy in range(y, y + h):
            self._px(x, yy, c); self._px(x + w - 1, yy, c)

    def text(self, *a):
        pass

    def show(self, *a):
        self.shows += 1

    def get(self, x, y):
        v = self.buffer[y * 120 + x // 2]
        return v >> 4 if x % 2 == 0 else v & 15


lcd = types.ModuleType("lcd")
lcd.LCD = LCD
lcd.color = lambda r, g, b: min(range(16), key=lambda i: sum((p - q) ** 2 for p, q in zip(BASE[i], (r, g, b))))
TINTS = {}


def tint(i, r, g, b):
    PAL[i] = (r, g, b)
    TINTS[i] = (r, g, b)


lcd.tint = tint
SCRIPT = []                                   # key presses to replay, one list per frame


class Keys:
    def pressed(self):
        return SCRIPT.pop(0) if SCRIPT else []

    def held(self, k):
        return False


lcd.Keys = Keys
sys.modules["lcd"] = lcd

ui = types.ModuleType("ui")
ui.WHITE, ui.INK, ui.MUTED, ui.GREEN, ui.GREEN_D, ui.GREY, ui.RED = 0, 1, 2, 3, 4, 5, 6
PAGES = []
ui.page = lambda d, head, lines, hint="": PAGES.append((head, lines, hint))
ui.progress = lambda *a, **k: PAGES.append(("progress",) + a)
ui.say = lambda *a, **k: None
ui.band = lambda *a, **k: None
sys.modules["ui"] = ui

SAVES = {}
save = types.ModuleType("save")
save.store = lambda n, v: SAVES.__setitem__(n, v)
save.load = lambda n, default=None: SAVES.get(n, default)
sys.modules["save"] = save

# net: answers getGraffitiBase from the fixture, totalSupply 104
GB5 = open(os.path.join(FIX, "gb5.hex")).read().strip()
net = types.ModuleType("net")


class NetError(Exception):
    pass


net.Error = NetError
ASKS = []


def chain(cid, method, params, *a, **k):
    assert method == "eth_call" and params[0]["data"] == "0x18160ddd", params
    return "0x" + "%064x" % 104


def ask(q):
    ASKS.append(q)
    return len(ASKS)


def answer(rid):
    q = ASKS[rid - 1]
    i = int(q["params"][0]["data"][10:], 16)
    if i == 5:
        return GB5
    raise NetError("no internet: test")


net.chain, net.ask, net.answer = chain, ask, answer
sys.modules["net"] = net

import time as _t
_t.ticks_ms = lambda: int(_t.monotonic() * 1000)
_t.ticks_diff = lambda a, b: a - b
_t.ticks_add = lambda a, b: a + b
_t.sleep_ms = lambda ms: None

ub = types.ModuleType("ubinascii")
ub.unhexlify = bytes.fromhex
sys.modules["ubinascii"] = ub

sys.path.insert(0, APP)
os.chdir(APP)
import graffiti_draw as G
import graffiti_chain as C
import graffiti as A


# ---- helpers
def bmp_bit(bmp, x, y):
    """Pixel (x, y), top-left origin, of the contract's 130x130 1bpp BMP."""
    row = 129 - y                              # bottom-up
    b = bmp[62 + row * 20 + x // 8]
    return (b >> (7 - x % 8)) & 1


def png(path, d):
    raw = b"".join(b"\0" + bytes(c for x in range(240) for c in PAL[d.get(x, y)]) for y in range(240))
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 240, 240, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


fails = 0


def check(name, ok, info=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("  " + info if info else ""))
    fails += not ok


snap = C.Snap()
check("snapshot count", snap.count() == 104, str(snap.count()))
buf = bytearray(C.BITS)
d = A.d
for i in (5, 42, 103):
    bmp = bytes.fromhex(open(os.path.join(FIX, "bmp%d.hex" % i)).read().strip()[2:])
    tid, color = snap.get(i, buf)
    pal = bmp[58:61]                           # palette[1] B, G, R
    check("token %d id" % i, tid == i)
    check("token %d color = BMP palette" % i, color == (pal[2] << 16 | pal[1] << 8 | pal[0]), "%06x" % color)
    bad = sum(1 for y in range(128) for x in range(128)
              if ((buf[y * 16 + x // 8] >> (7 - x % 8)) & 1) != bmp_bit(bmp, x + 1, y + 1))
    check("token %d bits = contract BMP" % i, bad == 0, "%d px differ" % bad)
    # full-screen scale: every screen pixel is the source pixel its table says
    d.fill(A.BLACK)
    G.scale(d.buffer, buf, G.TAB, A.FG | (A.BLACK << 4))
    bad = sum(1 for y in range(240) for x in range(240)
              if (d.get(x, y) == A.FG) != bool(bmp_bit(bmp, G.TAB[x] + 1, G.TAB[240 + y] + 1)))
    check("token %d scaled 240" % i, bad == 0, "%d px differ" % bad)
    tint(A.FG, color >> 16, (color >> 8) & 255, color & 255)
    png(os.path.join(OUT, "one-%d.png" % i), d)
    # thumbnail: on if any of 2x2 is on, nothing outside its box touched
    d.fill(A.BLACK)
    G.thumb(d.buffer, buf, 88 | (88 << 8), 9)
    bad = 0
    for y in range(240):
        for x in range(240):
            inside = 88 <= x < 152 and 88 <= y < 152
            want = inside and any(bmp_bit(bmp, 2 * (x - 88) + dx + 1, 2 * (y - 88) + dy + 1) for dx in (0, 1) for dy in (0, 1))
            bad += (d.get(x, y) == 9) != want
    check("token %d thumb" % i, bad == 0, "%d px differ" % bad)

# live decode against the same token from the snapshot
live = C.Live(11155111, "Sepolia", "0x47C630e06dB81eFa055Fa94EdE0A050e1150e56c")
check("live total", live.total() == 104)
check("live get queues", live.get(5, buf) is None and live.want == [5])
live.poll(); got = live.poll()
lb = bytearray(C.BITS)
r = live.get(5, lb)
snap.get(5, buf)
check("live token 5 = snapshot", got and r is not None and lb == buf and r[1] == snap.get(5, bytearray(C.BITS))[1])
live.get(6, lb); live.poll(); live.poll()
check("live error surfaces", live.err and "no internet" in live.err, str(live.err))

# palette slots for the wall don't collide with ui or black
check("9 free inks", len(A.INKS) >= 9 and A.BLACK not in A.INKS, str(A.INKS))

# ---- run the app's loop on a script of key presses
A.use(0)
d.shows = 0
frames = ([["right"]] + [[]] * 3 + [["Y"]] + [[]] * 2 + [["down"], ["right"], ["down"], ["press"]]
          + [[]] * 2 + [["A"]] + [[]] * 2 + [["A"]] + [["Y"]] + [["X"], ["right"], ["down"], ["right"], ["A"]])
SCRIPT[:] = frames


class Stop(Exception):
    pass


real_sleep = A.time.sleep_ms
calls = [0]


def sleep(ms):
    calls[0] += 1
    if not SCRIPT and calls[0] > len(frames) + 5:
        raise Stop
A.time.sleep_ms = sleep
seen = []
real_draw = A.draw


def draw():
    real_draw()
    seen.append((A.view, A.idx))
    png(os.path.join(OUT, "loop-%02d-%s-%d.png" % (len(seen), A.view, A.idx)), d)
A.draw = draw
try:
    A.run()
except Stop:
    pass
print("views drawn:", seen)
print("saves:", SAVES)
print("pages:", PAGES[-3:])
check("walked through views", ("wall", 1) in seen and ("show", 8) in seen)
check("settings saved", SAVES.get("cfg", {}).get("src") == 11155111 and SAVES["cfg"]["pace"] == 10000, str(SAVES.get("cfg")))
print("FAILS:", fails)
sys.exit(1 if fails else 0)
