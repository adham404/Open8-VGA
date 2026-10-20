"""SAVE/LOAD: the 25LC512 model on its own, then the firmware's F4/F6 through the editor."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import eeprom   # noqa: E402
import fwsim    # noqa: E402
import system   # noqa: E402

HZ = 3146875


def spi(e, data, now=0, keep_selected=False):
    """Bit-bang a frame in mode 0 like the firmware does; returns the bytes read."""
    out = []
    e.pins(0, now)                                  # /CS low, SCK low
    for byte in data:
        got = 0
        for i in range(7, -1, -1):
            bit = (byte >> i) & 1
            e.pins(bit << 1, now)                   # SCK low, data out
            e.pins((bit << 1) | 1, now)             # SCK high: sample
            got = (got << 1) | e.miso()
        out.append(got)
    e.pins(0, now)
    if not keep_selected:
        e.pins(4, now)                              # /CS high
    return out


class TestEEPROMModel(unittest.TestCase):
    def test_erased_reads_ff_and_status(self):
        e = eeprom.EEPROM25LC512()
        self.assertEqual(spi(e, [3, 0x12, 0x34, 0, 0, 0])[3:], [0xFF] * 3)
        self.assertEqual(spi(e, [5, 0])[1], 0)

    def test_write_needs_wren_and_takes_5ms(self):
        e = eeprom.EEPROM25LC512()
        spi(e, [2, 0, 0x10, 0xAB])
        self.assertEqual(e.mem[0x10], 0xFF)                      # no WREN: ignored
        spi(e, [6])
        self.assertEqual(spi(e, [5, 0])[1], 2)                   # WEL set
        spi(e, [2, 0, 0x10, 0xAB, 0xCD], now=1000)
        self.assertEqual(spi(e, [5, 0], now=1001)[1], 1)        # WIP, WEL cleared
        self.assertEqual(spi(e, [3, 0, 0x10, 0], now=1002)[3], 0xFF)   # busy: no reads
        later = 1000 + eeprom.WRITE_CYCLES
        self.assertEqual(spi(e, [5, 0], now=later)[1], 0)
        self.assertEqual(spi(e, [3, 0, 0x10, 0, 0], now=later)[3:], [0xAB, 0xCD])

    def test_page_wrap_and_sequential_read(self):
        e = eeprom.EEPROM25LC512()
        spi(e, [6])
        spi(e, [2, 0x01, 0x7E] + [1, 2, 3, 4])                   # page $0100-$017F
        self.assertEqual(list(e.mem[0x17E:0x180]), [1, 2])
        self.assertEqual(list(e.mem[0x100:0x102]), [3, 4])      # wrapped to the page start
        self.assertEqual(e.mem[0x180], 0xFF)
        got = spi(e, [3, 0x01, 0x7E, 0, 0, 0, 0], now=10 ** 6)[3:]
        self.assertEqual(got, [1, 2, 0xFF, 0xFF])                # reads do not wrap

    def test_frame_cut_short_does_not_write(self):
        e = eeprom.EEPROM25LC512()
        spi(e, [6])
        e.pins(0, 0)
        for bit in (1, 0, 1):                                   # 3 bits of a data byte only
            e.pins(bit << 1, 0)
            e.pins((bit << 1) | 1, 0)
        e.pins(4, 0)
        self.assertEqual(e.writes, 0)


def editor_with(text, s=None):
    """Boot to the editor and put `text` into the buffer (cursor at the end)."""
    s = s or fwsim.boot()
    assert s.run_until(s.sym["GK_L"])
    assert fwsim.press(s, " ")
    data = text.encode("latin-1")
    base = 0xB000 - 0x8000
    s.m.sram[base:base + len(data)] = data

    def put16(a, v):
        s.m.sram[a - 0x8000] = v & 0xFF
        s.m.sram[a - 0x8000 + 1] = v >> 8
    put16(0xFC02, 0xB000 + len(data))          # GAP_S
    put16(0xFC04, 0xF000)                      # GAP_E
    put16(0xFC06, 0xB000)                      # TOP
    put16(0xFC08, text.count("\n") + 1)        # CUR_LINE
    put16(0xFC0A, 1)                           # TOP_LINE
    s.m.sram[0xFC30 - 0x8000] = 1              # REDRAW
    assert fwsim.press(s, keys=["HOME"])
    return s


def buffer_text(s):
    r = lambda a: s.m.sram[a - 0x8000]
    gs = r(0xFC02) | r(0xFC03) << 8
    ge = r(0xFC04) | r(0xFC05) << 8
    return (bytes(r(a) for a in range(0xB000, gs)) + bytes(r(a) for a in range(ge, 0xF000))).decode("latin-1")


def message(s):
    return s.text_row(28).rstrip()


def save(s, slot, confirm=None):
    s.type(keys=["F4"])
    assert s.run_until(s.sym["GK_L"], max_cycles=20_000_000)          # slot screen
    s.type(str(slot))
    if confirm:
        s.run(200_000)
        assert s.run_until(s.sym["GK_L"], max_cycles=20_000_000)
        s.type(confirm)
    s.run(50_000)
    assert fwsim.wait_idle(s, max_cycles=200_000_000)


def load(s, slot, confirm="y"):
    s.type(keys=["F6"])
    assert s.run_until(s.sym["GK_L"], max_cycles=20_000_000)
    screen = "\n".join(fwsim.screen_text(s))
    s.type(str(slot))
    s.run(200_000)
    if confirm and s.run_until(s.sym["GK_L"], max_cycles=5_000_000):
        s.type(confirm)
        s.run(50_000)
    assert fwsim.wait_idle(s, max_cycles=200_000_000)
    return screen


PROGRAM = "; my program\n        LD A, #'!'\n        CALL PUTC\n        RET\n"


class TestSaveLoad(unittest.TestCase):
    def test_save_power_cycle_load(self):
        s = editor_with(PROGRAM)
        t0 = s.m.now
        save(s, 2)
        self.save_time = (s.m.now - t0) / HZ
        self.assertIn("Saved %d bytes, slot 2." % len(PROGRAM), message(s))
        self.assertEqual(buffer_text(s), PROGRAM)                        # editor text unchanged
        img = s.m.eeprom.mem
        self.assertEqual(bytes(img[0x4000:0x4004]), b"O8" + bytes([len(PROGRAM), 0]))
        self.assertEqual(bytes(img[0x4004:0x4004 + len(PROGRAM)]).decode(), PROGRAM)
        # power off: SRAM is lost, the EEPROM is not
        s2 = fwsim.boot()
        s2.m.eeprom = s.m.eeprom
        s2.m.eeprom.power_cycle()
        s2 = editor_with("", s2)
        screen = load(s2, 2)
        self.assertIn("2. ; my program   (%d bytes)" % len(PROGRAM), screen)
        self.assertIn("1. (empty)", screen)
        self.assertEqual(buffer_text(s2), PROGRAM)
        self.assertIn("Loaded %d bytes, slot 2." % len(PROGRAM), message(s2))
        self.assertTrue(fwsim.press(s2, keys=["F3"], label="GK_L"))       # and it runs
        self.assertEqual(s2.text_row(0)[0], "!")

    def test_four_independent_slots_and_overwrite_confirmation(self):
        s = editor_with("; one\n")
        save(s, 1)
        for n, text in ((2, "; two\n"), (3, "; three\n"), (4, "; four\n")):
            s.m.sram[0xB000 - 0x8000:0xB000 - 0x8000 + len(text)] = text.encode()
            s.m.sram[0xFC02 - 0x8000] = len(text)
            save(s, n)
        screen = load(s, 3)
        for n, name in ((1, "one"), (2, "two"), (3, "three"), (4, "four")):
            self.assertIn("%d. ; %s" % (n, name), screen)
        self.assertEqual(buffer_text(s), "; three\n")
        save(s, 1, confirm="n")                                          # refuse: slot 1 kept
        self.assertEqual(bytes(s.m.eeprom.mem[4:10]), b"; one\n")
        save(s, 1, confirm="y")
        self.assertEqual(bytes(s.m.eeprom.mem[4:12]), b"; three\n")

    def test_empty_slot(self):
        s = editor_with(PROGRAM)
        load(s, 4, confirm=None)
        self.assertIn("That slot is empty.", message(s))
        self.assertEqual(buffer_text(s), PROGRAM)

    def test_large_program_and_too_large(self):
        line = "        LD A, #1          ; a line of a long program\n"
        text = line * (16000 // len(line))
        s = editor_with(text)
        t0 = s.m.now
        save(s, 3)
        save_s = (s.m.now - t0) / HZ
        self.assertIn("Saved %d bytes, slot 3." % len(text), message(s))
        s2 = fwsim.boot()
        s2.m.eeprom = s.m.eeprom
        s2.m.eeprom.power_cycle()
        s2 = editor_with("", s2)
        t0 = s2.m.now
        load(s2, 3)
        load_s = (s2.m.now - t0) / HZ
        self.assertEqual(buffer_text(s2), text)
        self.assertLess(save_s, 8.0)
        self.assertLess(load_s, 4.0)
        print("\n  16 KB program: save %.1f s, load %.1f s at 3.15 MHz" % (save_s, load_s))
        big = "x" * 16381
        s3 = editor_with(big)
        save(s3, 1)
        self.assertIn("Too long to save", message(s3))
        self.assertEqual(s3.m.eeprom.writes, 0)

    def test_no_eeprom_fitted(self):
        s = editor_with(PROGRAM)
        s.m.eeprom = None
        s.type(keys=["F4"])
        s.run(100_000)
        self.assertTrue(fwsim.wait_idle(s, max_cycles=50_000_000))
        self.assertIn("No EEPROM found", message(s))

    def test_failed_write_is_reported(self):
        class Stuck(eeprom.EEPROM25LC512):
            def _end_frame(self, now):                                  # never stores data
                self.wel = False
        s = editor_with(PROGRAM)
        s.m.eeprom = Stuck()
        save(s, 1)
        self.assertIn("NOT saved", message(s))
        self.assertEqual(buffer_text(s), PROGRAM)


if __name__ == "__main__":
    unittest.main()
