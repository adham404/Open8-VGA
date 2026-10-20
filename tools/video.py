"""Open8-VGA video: timing ROM generator, pixel-accurate pipeline model, renderer, PNG.

Hardware being modelled (see docs/03-video-keyboard.md):
  H counter (0-99 chars) and V counter (0-524 lines), both 74HC163, clocked by CHAR CLK.
  Timing ROM (SST39SF010A) addressed by V[9:0]:H[6:0]; its output is registered (74HC574),
  so the signals for period k come from the ROM entry of period k-1.
  Tile pipeline, PIPE = 2 character periods:
    period n   phi1: VRAM read (row+SCROLL_Y, col+SCROLL_X)  -> char latch at mid-period
    period n+1 phi1: FONT read (char*16 + V[3:0])           -> font latch at mid-period
               end : font latch -> 74AC299 shift register (parallel load)
    period n+2     : 8 pixels shifted out at 25.175 MHz, gated by registered BLANK
  CPU access to VRAM/FONT happens only in phi2, after the video reads of that period.
"""
import struct
import sys
import zlib

DOT_HZ = 25_175_000
H_TOTAL, H_VISIBLE, H_FP, H_SYNC = 100, 80, 2, 12       # in 8-dot characters
V_TOTAL, V_VISIBLE, V_FP, V_SYNC = 525, 480, 10, 2      # in lines
PIPE = 2
FRAME_CYCLES = H_TOTAL * V_TOTAL                        # CPU cycles per frame (52 500)

HSYNC_N, VSYNC_N, BLANK, HRESET, VRESET, VBL_START = 1, 2, 4, 8, 16, 32
VBL_POS = V_VISIBLE * H_TOTAL + PIPE                    # frame position where VBLANK latch sets


def pixel_signals(pc, line):
    """Desired outputs while the pixels of character position pc on `line` are shown."""
    s = 0
    if not (pc < H_VISIBLE and line < V_VISIBLE):
        s |= BLANK
    if not (H_VISIBLE + H_FP <= pc < H_VISIBLE + H_FP + H_SYNC):
        s |= HSYNC_N
    if not (V_VISIBLE + V_FP <= line < V_VISIBLE + V_FP + V_SYNC):
        s |= VSYNC_N
    return s


def counter_signals(h, v):
    """Signals the *register* must present during the period with counters (h, v)."""
    pc, line = h - PIPE, v
    if pc < 0:
        pc += H_TOTAL
        line = (v - 1) % V_TOTAL
    s = pixel_signals(pc, line)
    if h == H_TOTAL - 1:
        s |= HRESET
        if v == V_TOTAL - 1:
            s |= VRESET
    if (h, v) == (PIPE, V_VISIBLE):
        s |= VBL_START
    return s


def build_timing_rom():
    rom = bytearray(1 << 17)
    for v in range(1024):
        for h in range(128):
            # Entry (h, v) is what the register outputs during the *next* period.
            if v >= V_TOTAL or h >= H_TOTAL:
                rom[(v << 7) | h] = HSYNC_N | VSYNC_N | BLANK | HRESET | (VRESET if v >= V_TOTAL else 0)
                continue
            nh, nv = (h + 1, v) if h + 1 < H_TOTAL else (0, (v + 1) % V_TOTAL)
            rom[(v << 7) | h] = counter_signals(nh, nv)
    return rom


class VideoModel:
    """Character-clock model of the counters, registered timing ROM and tile pipeline."""

    def __init__(self, timing_rom=None):
        self.rom = timing_rom or build_timing_rom()
        self.h = self.v = 0
        self.reg = counter_signals(0, 0)
        self.char_latch = 0
        self.font_latch = 0
        self.shift = 0

    def char_tick(self, vram, font, sx, sy, cpu_access=None):
        """One character period. Returns (8 pixel bits, hsync_n, vsync_n, vbl_start).

        cpu_access: optional callable run in phi2 (after the video reads), modelling a
        CPU read/write of VRAM/FONT in the same cycle.
        """
        out_pixels = 0 if self.reg & BLANK else self.shift
        result = (out_pixels, bool(self.reg & HSYNC_N), bool(self.reg & VSYNC_N),
                  bool(self.reg & VBL_START), bool(self.reg & BLANK))
        # phi1: video reads
        row = ((self.v >> 4) + sy) & 31
        col = (self.h + sx) & 127
        new_char = vram[row * 128 + col]
        new_font = font[self.char_latch * 16 + (self.v & 15)]
        # phi2: CPU access
        if cpu_access:
            cpu_access()
        # clock edge
        self.shift = new_font
        self.char_latch = new_char
        reg_now = self.reg
        self.reg = self.rom[(self.v << 7) | self.h]
        if reg_now & HRESET:
            self.h = 0
            self.v = 0 if reg_now & VRESET else self.v + 1
        else:
            self.h += 1
        return result

    def dot_stream(self, vram, font, sx=0, sy=0, chars=FRAME_CYCLES):
        """Yields (pixel, hsync_n, vsync_n, blank) per dot."""
        for _ in range(chars):
            px, hs, vs, _, bl = self.char_tick(vram, font, sx, sy)
            for bit in range(7, -1, -1):
                yield (px >> bit) & 1, hs, vs, bl


def render(vram, font, sx=0, sy=0):
    """Fast reference renderer: what the monitor should show. Returns 480 rows of 640 bits."""
    rows = []
    for y in range(480):
        tr = ((y >> 4) + sy) & 31
        line = []
        for c in range(80):
            ch = vram[tr * 128 + ((c + sx) & 127)]
            b = font[ch * 16 + (y & 15)]
            line.extend((b >> (7 - i)) & 1 for i in range(8))
        rows.append(line)
    return rows


def capture_like_monitor(dots):
    """Recover the 640x480 image from a dot stream using only the sync pulses, as a monitor does."""
    dots = list(dots)
    # find the first vsync falling edge, then sample lines relative to hsync falling edges
    def falling(seq_get, start):
        for i in range(start + 1, len(dots)):
            if seq_get(i - 1) and not seq_get(i):
                return i
        return None
    vs = falling(lambda i: dots[i][2], 0)
    hs_edges = []
    i = vs - 800 if vs and vs >= 800 else 0
    while True:
        e = falling(lambda k: dots[k][1], i)
        if e is None:
            break
        hs_edges.append(e)
        i = e
    # the first visible line starts V_SYNC + back porch lines after vsync
    first = next(k for k, e in enumerate(hs_edges) if e > vs - 400) + V_SYNC + 33
    rows = []
    for e in hs_edges[first:first + 480]:
        start = e + 96 + 48
        rows.append([dots[start + x][0] for x in range(640)])
    return rows, dots, vs, hs_edges


TINTS = {"white": (255, 255, 255), "green": (51, 255, 102), "amber": (255, 176, 0)}


def write_png(path, rows, tint="green", scale=1):
    fg = TINTS[tint]
    bg = (0, 0, 0)
    h, w = len(rows) * scale, len(rows[0]) * scale
    raw = bytearray()
    for r in rows:
        line = bytearray()
        for p in r:
            line += bytes(fg if p else bg) * scale
        for _ in range(scale):
            raw += b"\x00" + line
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main(path):
    with open(path, "wb") as f:
        f.write(build_timing_rom())
    print("wrote", path, "131072 bytes (SST39SF010A) — %.3f Hz frame" % (DOT_HZ / (800 * 525)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/rom/vga_timing.bin")
