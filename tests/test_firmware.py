"""Phase 4 verification: boot firmware, runtime, keyboard driver, editor and on-board assembler,
all executed by the simulated CPU from the real flash image."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import asm      # noqa: E402
import fwsim    # noqa: E402
import isa      # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FUZZ = int(os.environ.get("OPEN8_FUZZ", "12"))


def ref_bytes(src, gap=0xEE):
    """Reference bytes from $8000 to the last byte; gaps (from .org) hold `gap`,
    which is what assemble_onboard pre-fills user memory with."""
    img, _ = asm.assemble(src, limit=0xAEFF)
    if not img:
        return b""
    return bytes(img.get(a, gap) for a in range(0x8000, max(img) + 1))


def ref_error_line(src):
    try:
        asm.assemble(src, limit=0xAEFF)
    except asm.AsmError as e:
        return e.line
    return None


def ram(s, a):
    return s.m.sram[a - 0x8000]


def ram16(s, a):
    return ram(s, a) | ram(s, a + 1) << 8


def buffer_text(s):
    gs, ge = ram16(s, 0xFC02), ram16(s, 0xFC04)
    data = bytes(ram(s, a) for a in range(0xB000, gs)) + bytes(ram(s, a) for a in range(ge, 0xF000))
    return data.decode("latin-1"), gs - 0xB000


def message(s):
    return s.text_row(28).rstrip()


def editor(text=None):
    """Boot to the editor; optionally replace the text (F9 + typing)."""
    s = fwsim.boot()
    assert s.run_until(s.sym["GK_L"])
    assert fwsim.press(s, " ")
    if text is not None:
        s.type(keys=["F9"])
        assert s.run_until(s.sym["AY_L"])
        assert fwsim.press(s, "y")
        assert fwsim.press(s, text)
    return s


def ready():
    """Booted machine waiting at the welcome screen, so runtime routines can be called."""
    s = fwsim.boot()
    assert s.run_until(s.sym["GK_L"])
    return s


class TestOnMicrocodeCPU(unittest.TestCase):
    def test_boot_edit_assemble_run_cycle_accurate(self):
        """Same firmware on the microcode-level CPU (executes the real control ROM)."""
        s = fwsim.boot(fast=False)
        self.assertTrue(s.run_until(s.sym["GK_L"], max_cycles=5_000_000))
        self.assertIn("Welcome!", s.text_row(2))
        self.assertTrue(fwsim.press(s, " ", max_cycles=5_000_000))
        self.assertIn("HELLO", s.text_row(1))
        s.type(keys=["F3"])
        self.assertTrue(s.run_until(s.sym["GK_L"], max_cycles=10_000_000))
        self.assertEqual(s.text_row(0).rstrip(), "Hello from Open8-VGA!")
        self.assertIn("Program finished", s.text_row(2))


class TestBuild(unittest.TestCase):
    def test_image_layout(self):
        flash, a, stats = fwsim.build_firmware.build()
        self.assertEqual(len(flash), 128 * 1024)
        self.assertLess(stats["fixed_bytes"], 0x4000)
        for i, name in enumerate(asm.RUNTIME):
            self.assertEqual(a.symbols[name], 3 + 3 * i)
            self.assertEqual(flash[3 + 3 * i], isa.BY_OPCODE[flash[3 + 3 * i]].opcode)


class TestOnboardAssembler(unittest.TestCase):
    def check(self, src):
        ok, res, s = fwsim.assemble_onboard(src)
        ref_line = ref_error_line(src)
        if ref_line is None:
            self.assertTrue(ok, "on-board error %s for:\n%s" % (res, src))
            self.assertEqual(res, ref_bytes(src), src)
        else:
            self.assertFalse(ok, "on-board accepted, reference error at line %d:\n%s" % (ref_line, src))
            self.assertEqual(res[1], ref_line, "error line differs (code %d):\n%s" % (res[0], src))
        return ok, res

    def test_examples(self):
        for f in sorted(os.listdir(os.path.join(ROOT, "examples"))):
            if f[:2].isdigit():
                self.check(fwsim.build_firmware.example_text(f))

    def test_every_instruction_form(self):
        lines = ["here:"]
        for ins in isa.INSTRS:
            ops = [{"imm8": "#$12", "imm16": "#here+$1234", "abs": "[here + 3]", "ind": "[X]",
                    "indinc": "[ x+ ]", "addr": "here - 1"}.get(o, o) for o in ins.operands]
            lines.append("    %s %s" % (ins.mnem.lower(), ", ".join(ops)))
        for alias in asm.ALIASES:
            lines.append("    %s here" % alias)
        self.check("\n".join(lines))

    def test_literals_expressions_directives(self):
        self.check("""
VAL = 10
NEG = -2
        .db 255, $FF, 0xff, %11111111, 0b11111111, 'A', VAL+VAL+1, <$1234, >$1234
        .db '\\n', ';', "semi;colon\\n", "tab\\there", 0, NEG
        .dw label, $ - 1, end - label
label:  LD A, #VAL - 11        ; negative immediate
        LD A, #'z'
        LD X, #label + 2
        ST A, [label+1]
        .ds 3, $EE
        .ds VAL
        .org $8100
end:    JMP label
        """)

    def test_random_programs(self):
        rng = random.Random(42)
        forms = isa.INSTRS
        for n in range(FUZZ):
            labels = ["L%d_%s" % (i, "abcdefgh"[i % 8]) for i in range(12)]
            lines = ["K%d = %d" % (i, rng.randrange(-100, 300)) for i in range(3)]
            for i in range(60):
                if rng.random() < 0.2 and labels:
                    lines.append("%s:" % labels.pop())
                r = rng.random()
                if r < 0.1:
                    lines.append("    .db %d, \"x%d\", K0" % (rng.randrange(256), i))
                    continue
                if r < 0.15:
                    lines.append("    .dw L%d_%s - 2" % (rng.randrange(12), "abcdefgh"[0]))
                    continue
                ins = rng.choice(forms)
                ops = []
                for o in ins.operands:
                    tgt = "L%d_%s" % (rng.randrange(12), "abcdefgh"[rng.randrange(12) % 8])
                    ops.append({"imm8": "#%d" % rng.randrange(256), "imm16": "#%s" % tgt,
                                "abs": "[%s+1]" % tgt, "ind": "[X]", "indinc": "[X+]",
                                "addr": tgt}.get(o, o))
                lines.append("    %s %s ; comment %d" % (ins.mnem, ", ".join(ops), i))
            lines += ["%s: NOP" % l for l in labels]
            # every L*_* name used must exist: define the full grid at the end
            used = {"L%d_%s" % (a, b) for a in range(12) for b in "abcdefgh"}
            defined = {l.split(":")[0].strip() for l in lines if l.strip().endswith(":") or ": NOP" in l}
            lines += ["%s: .db %d" % (u, k) for k, u in enumerate(sorted(used - defined))]
            self.check("\n".join(lines))

    def test_errors_match_reference_line(self):
        cases = [
            "NOP\nFROB A",
            "NOP\nNOP\nLD A, X",
            "JMP nowhere",
            "NOP\nLD A, #300",
            "x1: NOP\nx1: NOP",
            "a: NOP",
            "ld: NOP",
            "NOP\n.db 1,\nNOP",
            "LD A, #$12G",
            "NOP\n.bogus 3",
            "LD A, [X",
            "LD A, #'ab'",
            "start: JMP start\n.ds 12000",
            ".org $AEFF\nNOP\nNOP",
            "NOP\n\n\n   ; comment only\nJZ missing",
            ".db \"unterminated",
            "VAL = 5\nVAL = 6",
            "LD A, B, A",
            "PUSH SP",
        ]
        for src in cases:
            self.check(src)

    def test_error_codes(self):
        expect = {"FROB A": 1, "LD A, X": 2, "JMP nowhere": 3, "x1: NOP\nx1: NOP": 4,
                  "LD A, #300": 5, ".org $AEFF\nNOP\nNOP": 6, "LD A, #$1G": 9,
                  ".bogus": 11, "a: NOP": 13, "LD A, [X": 8}
        for src, code in expect.items():
            ok, res, s = fwsim.assemble_onboard(src)
            self.assertFalse(ok, src)
            self.assertEqual(res[0], code, src)

    def test_symbol_table_capacity(self):
        src = "\n".join("name_%03d: NOP" % i for i in range(192))
        ok, res, s = fwsim.assemble_onboard(src)
        self.assertTrue(ok)
        ok, res, s = fwsim.assemble_onboard(src + "\nextra: NOP")
        self.assertEqual(res, (7, 193))

    def test_name_length_limit(self):
        ok, res, s = fwsim.assemble_onboard("abcdefghijklmn: NOP\nJMP abcdefghijklmn")
        self.assertTrue(ok)
        ok, res, s = fwsim.assemble_onboard("NOP\nabcdefghijklmno: NOP")
        self.assertEqual(res, (10, 2))


class TestEditor(unittest.TestCase):
    def test_type_assemble_run_return(self):
        prog = ("start:  CALL CLS\n        LD X, #msg\n        CALL PRINT\n        RET\n"
                "msg:    .db \"Typed on the keyboard!\", 0\n")
        s = editor(prog)
        self.assertEqual(buffer_text(s)[0], prog)
        self.assertTrue(fwsim.press(s, keys=["F2"]))
        self.assertIn("Assembled OK: %d bytes" % len(ref_bytes(prog)), message(s))
        s.type(keys=["F3"])
        self.assertTrue(s.run_until(s.sym["GK_L"]))
        self.assertEqual(s.text_row(0).rstrip(), "Typed on the keyboard!")
        self.assertIn("Program finished", s.text_row(1))
        self.assertTrue(fwsim.press(s, " "))
        self.assertEqual(buffer_text(s)[0], prog)            # source intact after the run

    def test_error_moves_cursor_to_line(self):
        prog = "        NOP\n        NOP\n        FROB A\n        NOP\n"
        s = editor(prog)
        self.assertTrue(fwsim.press(s, keys=["F2"]))
        self.assertIn("Error in line 3: unknown instruction", message(s))
        self.assertEqual(ram16(s, 0xFC08), 3)                 # CUR_LINE
        self.assertEqual(buffer_text(s)[1], prog.index("        FROB"))

    def test_random_editing_matches_model(self):
        rng = random.Random(5)
        s = editor("")
        text, cur, want = "", 0, 0

        def col():
            return cur - (text.rfind("\n", 0, cur) + 1)

        def home():
            return text.rfind("\n", 0, cur) + 1

        def endl():
            e = text.find("\n", cur)
            return len(text) if e < 0 else e

        def tocol(p):
            n = 0
            while n < want and p < len(text) and text[p] != "\n":
                p += 1
                n += 1
            return p

        for step in range(220):
            r = rng.random()
            if r < 0.45:
                ch = rng.choice("abcXYZ019 ;:#$[]+-")
                if col() < 79:
                    text, cur = text[:cur] + ch + text[cur:], cur + 1
                s.type(ch)
                want = col()
            elif r < 0.53:
                text, cur = text[:cur] + "\n" + text[cur:], cur + 1
                s.type(keys=["\n"]) if False else s.type("\n")
                want = col()
            elif r < 0.61:
                if cur > 0:
                    text, cur = text[:cur - 1] + text[cur:], cur - 1
                s.type("\b")
                want = col()
            elif r < 0.66:
                text = text[:cur] + text[cur + 1:]
                s.type(keys=["DELETE"])
                want = col()
            elif r < 0.74:
                cur = max(0, cur - 1)
                s.type(keys=["LEFT"])
                want = col()
            elif r < 0.82:
                cur = min(len(text), cur + 1)
                s.type(keys=["RIGHT"])
                want = col()
            elif r < 0.88:
                cur = home()
                if cur > 0:                 # on the first line UP goes to its start
                    cur -= 1
                    cur = home()
                    cur = tocol(cur)
                s.type(keys=["UP"])
            elif r < 0.94:
                cur = endl()
                if cur < len(text):
                    cur += 1
                    cur = tocol(cur)
                s.type(keys=["DOWN"])
            elif r < 0.97:
                cur = home()
                s.type(keys=["HOME"])
                want = 0
            else:
                cur = endl()
                s.type(keys=["END"])
                want = col()
            self.assertTrue(fwsim.press(s))
            got, gcur = buffer_text(s)
            self.assertEqual((got, gcur), (text, cur), "after step %d" % step)
        # the screen shows the text (lines visible from TOP)
        self.assertEqual(ram16(s, 0xFC08), text[:cur].count("\n") + 1)

    def test_scrolling_long_text(self):
        prog = "".join("line%d: NOP\n" % i for i in range(60))
        s = editor(prog)
        self.assertEqual(ram16(s, 0xFC08), 61)
        self.assertEqual(s.text_row(26).rstrip(), "line59: NOP")
        for _ in range(3):
            self.assertTrue(fwsim.press(s, keys=["PGUP"]))
        self.assertEqual(ram16(s, 0xFC0A), 1)                 # TOP_LINE
        self.assertEqual(s.text_row(2).rstrip(), "line1: NOP")
        self.assertTrue(fwsim.press(s, keys=["F2"]))
        self.assertIn("Assembled OK: 60 bytes", message(s))

    def test_reset_keeps_text(self):
        prog = "        LD A, #1\nloop:   JMP loop\n"
        s = editor(prog)
        s.type(keys=["F3"])
        s.run(2_000_000)                                       # program is in an endless loop
        s.cpu.pc, s.cpu.halted = 0, False                      # RESET button
        s.m.trap = s.m.violation = False
        self.assertTrue(fwsim.wait_idle(s))
        self.assertEqual(buffer_text(s)[0], prog)
        self.assertIn("reset", message(s))

    def test_invalid_instruction_is_reported(self):
        prog = "        NOP\n        .db $FF\n"
        s = editor(prog)
        self.assertTrue(fwsim.press(s, keys=["F3"]))
        self.assertIn("Invalid instruction at $8001", message(s))
        self.assertEqual(buffer_text(s)[0], prog)

    def test_protected_memory(self):
        prog = "        LD A, #$55\n        ST A, [$B000]\n        ST A, [$FC00]\n        RET\n"
        s = editor(prog)
        s.type(keys=["F3"])
        self.assertTrue(s.run_until(s.sym["GK_L"]))
        self.assertIn("protected system memory", s.text_row(0))
        self.assertTrue(fwsim.press(s, " "))
        self.assertEqual(buffer_text(s)[0], prog)

    def test_help_pages(self):
        s = editor()
        s.type(keys=["F1"])
        self.assertTrue(s.run_until(s.sym["HV_KEYS"]))
        self.assertIn("GETTING STARTED", s.text_row(1))
        pages = fwsim.build_firmware.help_pages()
        for p in range(1, len(pages)):
            s.type(keys=["PGDN"])
            s.run(30000)
            self.assertTrue(s.run_until(s.sym["HV_KEYS"]))
            self.assertEqual(s.text_row(1).rstrip(), pages[p].split("\n")[0])
        s.type(keys=["ESC"])
        self.assertTrue(fwsim.wait_idle(s))

    def test_examples_menu_loads_and_every_example_runs(self):
        s = editor()
        expected = {1: "Hello from Open8-VGA!", 2: "25 + 17 = 42", 3: "Count: 1",
                    4: "7 is odd and smaller than 100", 5: "Type something"}
        for n in range(1, 7):                 # 7 = Tetris, tested in test_games.py
            s.type(keys=["F5"])
            self.assertTrue(s.run_until(s.sym["GK_L"]))
            s.type(str(n))
            s.run(50000)
            self.assertTrue(s.run_until(s.sym["GK_L"]))
            self.assertTrue(fwsim.press(s, "y"))
            src = fwsim.build_firmware.example_text(fwsim.build_firmware.EXAMPLES[n - 1][1])
            self.assertEqual(buffer_text(s)[0], src)
            s.type(keys=["F3"])
            if n == 5:
                for part in ("H", "i", "!"):
                    s.run(3_000_000)
                    s.type(part)
                for key in ("UP", "ESC"):
                    s.run(3_000_000)
                    s.type(keys=[key])
            if n == 6:
                s.run(6_000_000)
                s.type(keys=["ESC"])
            self.assertTrue(s.run_until(s.sym["GK_L"], max_cycles=80_000_000), "example %d" % n)
            if n in expected:
                self.assertIn(expected[n], "\n".join(fwsim.screen_text(s)))
            if n == 2:
                self.assertIn("200 / 7 = 28 remainder 4", "\n".join(fwsim.screen_text(s)))
            if n == 5:
                self.assertIn("Hi!<80>", s.text_row(1))
            self.assertTrue(fwsim.press(s, " "))


class TestRuntime(unittest.TestCase):
    def test_prdec16_and_prhex(self):
        s = ready()
        for v in (0, 7, 10, 255, 1000, 40000, 65535):
            fwsim.call(s, "R_CLS")
            fwsim.call(s, "R_PRDEC16", {"x": v})
            self.assertEqual(s.text_row(0).rstrip(), str(v))
        fwsim.call(s, "R_CLS")
        fwsim.call(s, "R_PRHEX", {"a": 0xA7})
        self.assertEqual(s.text_row(0).rstrip(), "A7")

    def test_console_scrolls_with_hardware_register(self):
        s = ready()
        fwsim.call(s, "R_CLS")
        for i in range(33):
            fwsim.call(s, "R_PRDEC", {"a": i})
            fwsim.call(s, "R_NEWLINE")
        self.assertEqual(s.text_row(28).rstrip(), "32")      # visible row 28 after scrolling
        self.assertEqual(s.text_row(0).rstrip(), "4")
        self.assertNotEqual(s.m.scroll_y, 0)

    def test_getkey_codes(self):
        s = ready()
        cases = [("a", None, ord("a")), ("A", None, ord("A")), ("!", None, ord("!")),
                 (None, "UP", 0x80), (None, "LEFT", 0x82), (None, "F3", 0x92),
                 (None, "DELETE", 0x88), (None, "INSERT", 0x89), (None, "PGDN", 0x87),
                 (None, "F7", 0x96), (None, "F12", 0x9B),
                 (None, "ESC", 27), ("\n", None, 10), ("\b", None, 8)]
        for text, key, code in cases:
            s.type(text, [key] if key else [])
            self.assertTrue(fwsim.call(s, "R_GETKEY"))
            self.assertEqual(s.cpu.a, code, (text, key))

    def test_caps_lock_and_ctrl(self):
        s = ready()
        s.kb.type_bytes([0x58, 0xF0, 0x58] + [0x1C, 0xF0, 0x1C])      # Caps, a
        fwsim.call(s, "R_GETKEY")
        self.assertEqual(s.cpu.a, ord("A"))
        s.kb.type_bytes([0x14, 0x21, 0xF0, 0x21, 0xF0, 0x14])         # Ctrl+C
        fwsim.call(s, "R_GETKEY")
        self.assertEqual(s.cpu.a, 3)

    def test_keydown_tracks_held_keys(self):
        s = ready()
        s.kb.type_bytes([0xE0, 0x6B], s.m.now)                        # left arrow down
        s.run(20000)
        fwsim.call(s, "R_KEYDOWN", {"a": 0x6B})
        self.assertEqual(s.cpu.a, 1)
        s.kb.type_bytes([0xE0, 0xF0, 0x6B], s.m.now)                  # released
        s.run(20000)
        fwsim.call(s, "R_KEYDOWN", {"a": 0x6B})
        self.assertEqual(s.cpu.a, 0)

    def test_random_varies(self):
        s = ready()
        vals = set()
        for _ in range(64):
            fwsim.call(s, "R_RANDOM")
            vals.add(s.cpu.a)
        self.assertGreater(len(vals), 40)

    def test_bad_frames_are_ignored(self):
        s = ready()
        s.kb.inject_glitch(s.m.now + 10)
        s.run(5000)
        s.type("q")
        fwsim.call(s, "R_GETKEY")
        self.assertEqual(s.cpu.a, ord("q"))


if __name__ == "__main__":
    unittest.main()
