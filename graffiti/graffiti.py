# Graffiti: the Graffiti NFT collection on a wedgie. Each graffiti is 128x128, one color on black.
#
#   One     a graffiti over the whole screen. Left/right: the one before, the next.
#   Wall    nine at half size. The joystick moves; green or press opens one.
#   Show    a slideshow: the next one every few seconds. Green or press: pause.
#
#   Green: One -> Show, Wall -> One, Show -> pause.   Red: One -> Wall, Show -> One.
#   The grey button by the joystick (X): settings (where they come from, the slideshow's pace).
#   The other grey button (B), on One: ask the chain for this one again.
#
# Where from: the snapshot packed with the app (works with nothing plugged in, instant), or a chain,
# live (Sepolia, Base, Linea: graffiti_chains.json), through the wedgie's page on wedgie.dev.
import time
import gc
import lcd as L
import ui
import save
import graffiti_draw as G
import graffiti_chain as C

FRAME = 30
BADGE_MS = 1500
PACES = (3000, 5000, 10000)
CELL = 64
GAP = 12                                     # 3 x 64 + 4 x 12 = 240
CELLS = 9

d = L.LCD()
keys = L.Keys()
BUF = bytearray(C.BITS)                      # the one graffiti being drawn
BLACK = L.color(0, 0, 0)
# Palette slots tinted to a graffiti's color (a tint lasts until the next fill(), so every screen that
# isn't ours starts clean). The wall shows only black, the green cursor and grey empty cells; one
# graffiti, black and its white number.
INKS = [i for i in range(16) if i not in (BLACK, ui.GREEN, ui.GREY)]
FG = [i for i in INKS if i != ui.WHITE][0]

src = None
idx = 0
view = "one"
paused = False
cursor_shown = -1
badge_until = 0
next_at = 0
cfg = {"src": 0, "pace": 5000}               # src 0: the snapshot, else a chain id


def rgb(c):
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def tint(i, c):
    r, g, b = rgb(c)
    if hasattr(L, "tint"):
        L.tint(i, r, g, b)


def cell_xy(k):
    return GAP + (k % 3) * (CELL + GAP), GAP + (k // 3) * (CELL + GAP)


def wait(want):
    """Wait for one of these keys (names), real presses or not. Returns the one."""
    while True:
        for k in keys.pressed():
            if k in want:
                return k
        time.sleep_ms(FRAME)


# ---- where from


def use(chain):
    """Switch to the snapshot (0) or a chain. False if that chain can't be reached (we stay put)."""
    global src, idx
    if chain:
        for cid, name, address in C.chains():
            if cid == chain:
                break
        else:
            return False
        ui.progress("Graffiti on " + name, "how many", bar=False)
        try:
            new = C.Live(cid, name, address)
            n = new.total()
        except Exception as e:
            trouble(name, e)
            return False
        if not n:
            trouble(name, "none minted yet")
            return False
    else:
        new = C.Snap()
    if src:
        src.close()
    src = new
    gc.collect()
    idx = idx % src.count()
    return True


def trouble(name, e, hint="{g} ok"):
    """Say a chain didn't answer. Returns the key that closed it."""
    ui.page(d, "No answer", [(name, ui.INK), (str(e)[:28], ui.RED),
                             ("Keep its wedgie.dev", ui.MUTED), ("page open", ui.MUTED)], hint)
    return wait(("A", "press", "Y"))


# ---- drawing


def badge():
    """The graffiti's number, bottom left, for a moment."""
    global badge_until
    t = "#%d" % idx
    if src.live:
        t += " " + src.name
    if paused:
        t += " paused"
    w = 8 * len(t) + 8
    d.fill_rect(0, 228, w, 12, BLACK)
    d.text(t, 4, 230, ui.WHITE)
    badge_until = time.ticks_add(time.ticks_ms(), BADGE_MS)


def draw_one(with_badge=True):
    got = src.get(idx, BUF)
    if got is None:                          # live, on its way: poll() brings it, then we draw again
        ui.progress("Graffiti #%d" % idx, src.name, bar=False)
        return
    d.fill(BLACK)
    tint(FG, got[1])
    G.scale(d.buffer, BUF, G.TAB, FG | (BLACK << 4))
    if with_badge:
        badge()
    d.show()


def draw_wall():
    global cursor_shown
    page = idx // CELLS * CELLS
    d.fill(BLACK)
    for k in range(CELLS):
        i = page + k
        if i >= src.count():
            break
        x, y = cell_xy(k)
        got = src.get(i, BUF)
        if got is None:
            d.rect(x, y, CELL, CELL, ui.GREY)
            continue
        ink = INKS[k % len(INKS)]
        tint(ink, got[1])
        G.thumb(d.buffer, BUF, x | (y << 8), ink)
    cursor_shown = -1
    cursor()
    d.show()


def cursor():
    """Move the frame around the picked cell (only the two cells change)."""
    global cursor_shown
    k = idx % CELLS
    if cursor_shown == k:
        return
    if cursor_shown >= 0:
        x, y = cell_xy(cursor_shown)
        d.rect(x - 4, y - 4, CELL + 8, CELL + 8, BLACK)
        d.rect(x - 3, y - 3, CELL + 6, CELL + 6, BLACK)
    x, y = cell_xy(k)
    d.rect(x - 4, y - 4, CELL + 8, CELL + 8, ui.GREEN)
    d.rect(x - 3, y - 3, CELL + 6, CELL + 6, ui.GREEN)
    cursor_shown = k


def draw():
    if view == "wall":
        draw_wall()
    else:
        draw_one()


# ---- settings


def settings():
    """Up/down: which line. Left/right: change it. Green: keep. Red: back as it was."""
    options = [(0, "Snapshot")] + [(cid, name) for cid, name, _ in C.chains()]
    at = 0
    for k, (cid, _) in enumerate(options):
        if cid == cfg["src"]:
            at = k
    pace = PACES.index(cfg["pace"]) if cfg["pace"] in PACES else 1
    line = 0
    while True:
        d.fill(ui.WHITE)
        ui.band(d)
        ui.say(d, "Settings", 40, ui.INK, 2)
        for n, (label, value) in enumerate((("From", options[at][1]), ("Slideshow", "%d s" % (PACES[pace] // 1000)))):
            y = 90 + n * 44
            c = ui.INK if n == line else ui.MUTED
            ui.say(d, label, y, ui.MUTED)
            ui.say(d, ("< %s >" % value) if n == line else value, y + 14, c, 2)
        ui.say(d, "{g} keep  {r} back", 222, ui.MUTED)
        d.show()
        k = wait(("up", "down", "left", "right", "A", "press", "Y"))
        if k in ("up", "down"):
            line ^= 1
        elif k in ("left", "right"):
            step = 1 if k == "right" else -1
            if line == 0:
                at = (at + step) % len(options)
            else:
                pace = (pace + step) % len(PACES)
        elif k == "Y":
            return
        else:
            break
    cfg["pace"] = PACES[pace]
    want = options[at][0]
    if want != cfg["src"] and use(want):
        cfg["src"] = want
    try:
        save.store("cfg", cfg)
    except OSError:
        pass                                 # flash full: it still works, it just won't remember


# ---- the loop


def step(n):
    global idx, next_at
    if src.live:
        src.drop_wants()
    idx = (idx + n) % src.count()
    next_at = time.ticks_add(time.ticks_ms(), cfg["pace"])


def run():
    global view, paused, idx, next_at, badge_until
    c = save.load("cfg", None)
    if isinstance(c, dict):
        cfg.update(c)
    idx = save.load("at", 0)
    if not isinstance(idx, int) or idx < 0:
        idx = 0
    if not (cfg["src"] and use(cfg["src"])):
        cfg["src"] = 0
        use(0)
    saved_at, saved_t = idx, time.ticks_ms()
    redraw = True
    while True:
        t = time.ticks_ms()
        k = keys.pressed()
        if src.live and src.poll():
            if src.err:
                e, src.err = src.err, None
                if trouble(src.name, e, "{g} snapshot  {r} again") != "Y":
                    cfg["src"] = 0
                    use(0)
            redraw = True
        was = idx
        if view == "wall":
            if "left" in k:
                idx = (idx - 1) % src.count()
            elif "right" in k:
                idx = (idx + 1) % src.count()
            elif "up" in k:
                idx = (idx - 3) % src.count()
            elif "down" in k:
                idx = (idx + 3) % src.count()
            elif "A" in k or "press" in k:
                view, redraw = "one", True
            if idx != was:
                if idx // CELLS == was // CELLS:
                    cursor()
                    d.show()
                else:
                    if src.live:
                        src.drop_wants()
                    redraw = True
        else:
            if "left" in k:
                step(-1)
                redraw = True
            elif "right" in k:
                step(1)
                redraw = True
            if view == "one":
                if "A" in k or "press" in k:
                    view, paused, redraw = "show", False, True
                    next_at = time.ticks_add(t, cfg["pace"])
                elif "Y" in k:
                    view, redraw = "wall", True
                elif "B" in k and src.live:
                    src.forget(idx)
                    redraw = True
            else:
                if "A" in k or "press" in k:
                    paused = not paused
                    next_at = time.ticks_add(t, cfg["pace"])
                    badge()
                    d.show()
                elif "Y" in k:
                    view, redraw = "one", True
                elif not paused and time.ticks_diff(t, next_at) >= 0 and not src.busy():
                    step(1)
                    redraw = True
        if "X" in k:
            settings()
            redraw = True
        if badge_until and not redraw and view != "wall" and time.ticks_diff(t, badge_until) >= 0:
            badge_until = 0
            draw_one(False)                  # the same graffiti, without its number
        if redraw:
            redraw = False
            draw()
        if idx != saved_at and view != "show" and time.ticks_diff(t, saved_t) > 10000:
            saved_at, saved_t = idx, t           # where we are, at most every 10 s (flash wears)
            try:
                save.store("at", idx)
            except OSError:
                pass
        left = FRAME - time.ticks_diff(time.ticks_ms(), t)
        if left > 0:
            time.sleep_ms(left)
