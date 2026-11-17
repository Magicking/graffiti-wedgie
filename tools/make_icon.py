"""Draw the 12x12 wedgie.json icon from one graffiti in the snapshot (default: token 0).

python3 -I tools/make_icon.py [index] [--png out.png]

The same token 0 is on Sepolia (ids there match the snapshot ids).
Each icon cell covers about 10.7x10.7 source pixels; a cell is lit when enough of it is lit.
Lit cells use the palette letter closest to the graffiti's color, the rest are black.
"""
import json
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "graffiti", "graffiti_snap.bin")
MANIFEST = os.path.join(ROOT, "wedgie.json")
HEADER, META, BITS = 16, 32, 2048
N, SIZE = 12, 128
PALETTE = {"k": (0, 0, 0), "w": (255, 255, 255), "g": (0, 200, 0), "r": (220, 0, 0),
           "y": (255, 220, 0), "b": (0, 80, 255), "s": (128, 128, 128)}
THRESHOLD = 0.06


def load(index):
    with open(SNAP, "rb") as f:
        f.seek(HEADER + index * (META + BITS))
        meta = f.read(META)
        bits = f.read(BITS)
    tid = struct.unpack(">H", meta[:2])[0]
    return tid, tuple(meta[2:5]), bits


def lit(bits, x, y):
    return bits[y * 16 + x // 8] >> (7 - x % 8) & 1


def hue(c):
    r, g, b = c
    hi, lo = max(c), min(c)
    if hi == lo:
        return 0
    if hi == r:
        h = (g - b) / (hi - lo)
    elif hi == g:
        h = 2 + (b - r) / (hi - lo)
    else:
        h = 4 + (r - g) / (hi - lo)
    return h * 60 % 360


def box(bits):
    pts = [(x, y) for y in range(SIZE) for x in range(SIZE) if lit(bits, x, y)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    side = max(x1 - x0, y1 - y0)                       # square crop around the drawing
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    return cx - side // 2, cy - side // 2, side


def icon(bits, color):
    # pick the letter by hue, so a light green stays green (not yellow, grey or white)
    if max(color) - min(color) < 40:
        ink = "w" if sum(color) > 380 else "s"
    else:
        h = hue(color)
        ink = min("gryb", key=lambda k: min(abs(hue(PALETTE[k]) - h), 360 - abs(hue(PALETTE[k]) - h)))
    left, top, side = box(bits)
    rows = []
    for cy in range(N):
        y0, y1 = top + cy * side // N, top + (cy + 1) * side // N
        row = ""
        for cx in range(N):
            x0, x1 = left + cx * side // N, left + (cx + 1) * side // N
            on = sum(lit(bits, x, y) for y in range(y0, y1) for x in range(x0, x1)
                     if 0 <= x < SIZE and 0 <= y < SIZE)
            row += ink if on >= THRESHOLD * max(1, (x1 - x0) * (y1 - y0)) else "k"
        rows.append(row)
    return rows


def png(path, rows, color, scale=16):
    rgb = {k: v for k, v in PALETTE.items()}
    raw = b""
    for row in rows:
        line = b"".join(bytes(color if c != "k" else rgb["k"]) * scale for c in row)
        raw += (b"\0" + line) * scale
    w = h = N * scale

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    args = sys.argv[1:]
    out = None
    if "--png" in args:
        i = args.index("--png")
        out = args[i + 1]
        del args[i:i + 2]
    index = int(args[0]) if args else 0
    tid, color, bits = load(index)
    rows = icon(bits, color)
    with open(MANIFEST) as f:
        manifest = json.load(f)
    manifest["apps"][0]["icon"] = rows
    manifest["apps"][0]["label"] = "#%02x%02x%02x" % color
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    if out:
        png(out, rows, color)
    print("token", tid, "#%02x%02x%02x" % color)
    print("\n".join(rows))


main()
