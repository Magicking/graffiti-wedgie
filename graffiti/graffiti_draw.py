# Pixel work for Graffiti, in viper (integer only, at most 4 arguments: tables and colors are packed).
#
# A graffiti is 128x128 at 1 bit a pixel: 128 rows of 16 bytes, the leftmost pixel in the top bit
# (the contract's 64 uint256 words, as they are). The screen buffer (lcd.buffer) is 240x240 at 4 bits:
# 120 bytes a row, the left pixel of each byte in the high 4 bits.
import micropython

SIZE = 128
FULL = 240

# Nearest-neighbour tables for 128 -> 240 (x1.875): TAB[0:240] source column, TAB[240:480] source row.
TAB = bytearray(2 * FULL)
for _i in range(FULL):
    TAB[_i] = _i * SIZE // FULL
    TAB[FULL + _i] = _i * SIZE // FULL


@micropython.viper
def scale(dst: ptr8, src: ptr8, tab: ptr8, col: int):
    """The graffiti over the whole screen. col = fg | bg << 4 (palette indexes)."""
    fg = col & 15
    bg = (col >> 4) & 15
    last = -1
    for y in range(240):
        sy = int(tab[240 + y])
        row = y * 120
        if sy == last:                      # same source row as the one above: copy it
            p = row - 120
            for i in range(120):
                dst[row + i] = dst[p + i]
        else:
            last = sy
            s = sy * 16
            for bx in range(120):
                x0 = int(tab[2 * bx])
                x1 = int(tab[2 * bx + 1])
                hi = bg
                lo = bg
                if (src[s + (x0 >> 3)] >> (7 - (x0 & 7))) & 1:
                    hi = fg
                if (src[s + (x1 >> 3)] >> (7 - (x1 & 7))) & 1:
                    lo = fg
                dst[row + bx] = (hi << 4) | lo


@micropython.viper
def thumb(dst: ptr8, src: ptr8, pos: int, fg: int):
    """The graffiti at half size (64x64), a pixel on if any of its 2x2 is. pos = x | y << 8, x even.
    Only lit pixels are written: the background is what's already there."""
    ox = pos & 255
    oy = (pos >> 8) & 255
    for ty in range(64):
        s = ty * 32                         # source rows 2ty and 2ty+1
        row = (oy + ty) * 120 + (ox >> 1)
        for tb in range(32):                # 2 thumbnail pixels a byte: source columns 4tb..4tb+3
            c = tb * 4
            b = int(src[s + (c >> 3)]) | int(src[s + 16 + (c >> 3)])
            nib = (b >> (4 - (c & 7))) & 15
            if nib:
                v = int(dst[row + tb])
                hi = (v >> 4) & 15
                lo = v & 15
                if nib & 12:
                    hi = fg
                if nib & 3:
                    lo = fg
                dst[row + tb] = (hi << 4) | lo
