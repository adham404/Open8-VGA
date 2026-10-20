"""Phase 3 verification: VGA timing ROM + tile pipeline, PS/2 receiver, system integration."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import font    # noqa: E402
import ps2     # noqa: E402
import system  # noqa: E402
import video   # noqa: E402

FONT = font.build_font()


def edges(signal, falling=True):
    return [i for i in range(1, len(signal))
            if signal[i - 1] != signal[i] and signal[i] == (not falling)]


class TestVGATiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(7)
        cls.vram = bytes(rng.randrange(256) for _ in range(4096))
        vm = video.VideoModel()
        for _ in vm.dot_stream(cls.vram, FONT, chars=video.FRAME_CYCLES):   # settle
            pass
        cls.dots = list(vm.dot_stream(cls.vram, FONT, 9, 4, chars=video.FRAME_CYCLES * 2))
        cls.hs = [d[1] for d in cls.dots]
        cls.vs = [d[2] for d in cls.dots]
        cls.blank = [d[3] for d in cls.dots]

    def test_horizontal(self):
        fall = edges(self.hs)
        rise = edges(self.hs, falling=False)
        self.assertTrue(all(b - a == 800 for a, b in zip(fall, fall[1:])), "line != 800 dots")
        widths = {r - f for f, r in zip(fall, [r for r in rise if r > fall[0]])}
        self.assertEqual(widths, {96})
        # front porch: 16 dots from the end of a visible line to the hsync falling edge
        vis_end = edges(self.blank, falling=False)          # blank rises at end of visible
        fp = {next(f for f in fall if f > e) - e for e in vis_end[:400]}
        self.assertEqual(fp, {16})
        vis_start = edges(self.blank, falling=True)
        bp = {s - max(r for r in rise if r < s) for s in vis_start[1:400]}
        self.assertEqual(bp, {48})

    def test_vertical(self):
        vfall = edges(self.vs)
        vrise = edges(self.vs, falling=False)
        self.assertEqual(vfall[1] - vfall[0], 800 * 525)
        self.assertEqual(next(r for r in vrise if r > vfall[0]) - vfall[0], 800 * 2)
        visible_lines = [i for i in range(800 * 525) if not self.blank[vfall[0] + i]]
        self.assertEqual(len(visible_lines), 640 * 480)
        self.assertAlmostEqual(video.DOT_HZ / (800 * 525), 59.94, places=2)
        self.assertTrue(all(not v for v in self.vs) is False)   # sync is active-low pulses

    def test_pipeline_matches_reference_renderer(self):
        rows, *_ = video.capture_like_monitor((d[0], d[1], d[2]) for d in self.dots)
        self.assertEqual(rows, video.render(self.vram, FONT, 9, 4))
        self.assertGreater(sum(map(sum, rows)), 10000)        # not a blank screen

    def test_wrong_pipeline_delay_is_detected(self):
        saved = video.PIPE
        try:
            video.PIPE = 1
            rom = video.build_timing_rom()
        finally:
            video.PIPE = saved
        vm = video.VideoModel(rom)
        for _ in vm.dot_stream(self.vram, FONT, chars=video.FRAME_CYCLES):
            pass
        dots = vm.dot_stream(self.vram, FONT, chars=video.FRAME_CYCLES * 2)
        rows, *_ = video.capture_like_monitor((d[0], d[1], d[2]) for d in dots)
        self.assertNotEqual(rows, video.render(self.vram, FONT))

    def test_scroll_wraps_tilemap(self):
        vram = bytearray(4096)
        vram[0 * 128 + 120] = ord("A")            # column 120 of row 0
        vram[31 * 128 + 0] = ord("B")             # row 31, column 0
        r = video.render(vram, FONT, sx=120, sy=0)
        self.assertEqual(r[2][:8], [(FONT[ord("A") * 16 + 2] >> (7 - i)) & 1 for i in range(8)])
        r = video.render(vram, FONT, sx=0, sy=31)
        self.assertEqual(r[2][:8], [(FONT[ord("B") * 16 + 2] >> (7 - i)) & 1 for i in range(8)])

    def test_cpu_access_in_phi2_never_disturbs_current_fetch(self):
        vram = bytearray(4096)
        vram[5] = 0x41
        vm = video.VideoModel()
        while not (vm.h == 5 and vm.v == 0):
            vm.char_tick(vram, FONT, 0, 0)
        def cpu_write():
            vram[5] = 0x42                        # same cell, same character period
        vm.char_tick(vram, FONT, 0, 0, cpu_access=cpu_write)
        self.assertEqual(vm.char_latch, 0x41)     # video got the old value this period
        self.assertEqual(vram[5], 0x42)           # CPU write landed

    def test_counters_recover_from_illegal_states(self):
        vm = video.VideoModel()
        vm.h, vm.v = 120, 700
        for _ in range(3 * video.H_TOTAL):
            vm.char_tick(bytes(4096), FONT, 0, 0)
        self.assertLess(vm.h, video.H_TOTAL)
        self.assertLess(vm.v, video.V_TOTAL)


def drain(kb, rx, reads_every=0, total=200_000):
    """Drive the keyboard model; read bytes like a CPU polling every `reads_every` cycles."""
    got = []
    t = 0
    while t < total:
        t += 50
        kb.advance(t)
        if rx.ready and (reads_every == 0 or t % reads_every < 50):
            st = rx.status(t)
            got.append((rx.read_data(), st))
    return got


class TestPS2(unittest.TestCase):
    def test_every_byte_value_and_status_bits(self):
        rx = ps2.Receiver()
        kb = ps2.Keyboard(rx)
        got, t = [], 0
        for b in range(256):                      # one key at a time, like a typist
            kb.type_bytes([b], t)
            while not rx.ready:
                t += 50
                kb.advance(t)
            st = rx.status(t)
            got.append((rx.read_data(), st))
        self.assertEqual([g[0] for g in got], list(range(256)))
        for value, st in got:
            self.assertEqual(st & 1, 1)                       # READY
            self.assertEqual((st >> 2) & 1, 0)                # start bit 0
            self.assertEqual((st >> 3) & 1, 1)                # stop bit 1
            parity = (st >> 1) & 1
            self.assertEqual((bin(value).count("1") + parity) & 1, 1)   # odd parity

    def test_inhibit_prevents_loss_with_slow_cpu(self):
        rx = ps2.Receiver()
        kb = ps2.Keyboard(rx)
        data = ps2.text_to_scancodes("hi")        # 6 bytes
        kb.type_bytes(data)
        got = drain(kb, rx, reads_every=20_000, total=400_000)
        self.assertEqual([g[0] for g in got], data)

    def test_keyboard_buffer_overrun_reports_00(self):
        rx = ps2.Receiver()
        kb = ps2.Keyboard(rx)
        kb.type_bytes(list(range(1, 21)))          # 20 bytes into a 16-byte buffer
        got = [g[0] for g in drain(kb, rx, total=400_000)]
        self.assertEqual(got, list(range(1, 17)) + [ps2.OVERRUN])

    def test_noise_glitch_is_cleared_by_timeout(self):
        rx = ps2.Receiver()
        kb = ps2.Keyboard(rx)
        kb.inject_glitch(10)
        kb.next_time = 10 + ps2.TIMEOUT_CYCLES + 100
        kb.type_bytes([0x1C], 10)
        got = drain(kb, rx, total=40_000)
        self.assertEqual(got[0][0], 0x1C)

    def test_glitch_inside_frame_is_detectable(self):
        rx = ps2.Receiver()
        kb = ps2.Keyboard(rx)
        kb.type_bytes([0x1C])
        kb.advance(0)
        kb.inject_glitch(100)                     # extra edge before the real frame ends
        got = drain(kb, rx, total=40_000)
        value, st = got[0]
        start, stop, parity = (st >> 2) & 1, (st >> 3) & 1, (st >> 1) & 1
        frame_ok = start == 0 and stop == 1 and (bin(value).count("1") + parity) & 1
        self.assertFalse(frame_ok)

    def test_decoder_round_trip(self):
        text = 'LD A, #$1F ; "Hi" {x}|~\n'
        d = ps2.Decoder()
        out = []
        for b in ps2.text_to_scancodes(text) + ps2.press("UP") + ps2.press("F1"):
            ev = d.feed(b)
            if ev:
                out.append(ev)
        chars = "".join(e[1] for e in out if e[0] == "char")
        self.assertEqual(chars, text)
        self.assertEqual(out[-2:], [("key", "UP"), ("key", "F1")])
        self.assertEqual(d.down, set())           # every make had its break


HEX_ECHO = """
; Wait for three PS/2 bytes and print each as two hex digits on row 0.
        LD X, #VRAM
        LD B, #3
next:   LD A, [KBD_STATUS]
        AND A, #1
        JZ next
        LD A, [KBD_DATA]
        PUSH A
        SHR A
        SHR A
        SHR A
        SHR A
        CALL hexdig
        POP A
        AND A, #$0F
        CALL hexdig
        LD A, #' '
        ST A, [X+]
        DEC B
        JNZ next
        HLT
hexdig: CMP A, #10
        JC digit
        ADD A, #'A'-10
        ST A, [X+]
        RET
digit:  ADD A, #'0'
        ST A, [X+]
        RET
"""

VBLANK_COUNT = """
; Count three vertical blanks, then halt.
        LD B, #3
wait:   LD A, [SYS_STATUS]
        AND A, #1
        JZ wait
        DEC B
        JNZ wait
        HLT
"""


class TestSystem(unittest.TestCase):
    def test_keyboard_to_screen_through_real_program(self):
        s = system.System()
        s.load_user_program(HEX_ECHO)
        s.type("a")
        self.assertTrue(s.run_until_halt(2_000_000))
        self.assertEqual(s.text_row(0, 0, 9), "1C F0 1C ")

    def test_vblank_paces_frames(self):
        s = system.System()
        s.load_user_program(VBLANK_COUNT)
        self.assertTrue(s.run_until_halt(1_000_000))
        frames = s.m.now / video.FRAME_CYCLES
        self.assertGreater(frames, 2.0)
        self.assertLess(frames, 3.1)


if __name__ == "__main__":
    unittest.main()
