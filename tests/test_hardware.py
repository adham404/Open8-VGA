"""Phase 5/6: the board netlist (hardware/design.py) simulated at chip-pin level.

These tests run real programs through the netlist's own wiring (every 74xx pin, the ROM
images, buses and strobes) and compare with the verified CPU models."""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "hardware"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import asm       # noqa: E402
import design    # noqa: E402
import eeprom    # noqa: E402
import gatesim   # noqa: E402
import isa       # noqa: E402
import ps2       # noqa: E402
import sim       # noqa: E402
import video     # noqa: E402

ROMS = gatesim.load_roms()
DESIGN = design.build()


def rom_with(program):
    """Firmware flash image with `program` assembled at $0000."""
    img, a = asm.assemble(program, origin=0)
    flash = bytearray(ROMS["firmware"])
    for addr, v in img.items():
        flash[addr] = v
    return bytes(flash), a


def board(flash=None):
    roms = dict(ROMS)
    if flash is not None:
        roms["firmware"] = flash
    b = gatesim.Board(roms, DESIGN)
    b.set_ext("RSTRAW_N", 0)
    b.run_cycles(4)
    b.set_ext("RSTRAW_N", None)
    return b


def run_until_halt(b, max_cycles):
    for _ in range(max_cycles):
        if b.nets["HALTED"]:
            return True
        b.run_cycles(1)
    return bool(b.nets["HALTED"])


EVERY_INSTRUCTION = None


def every_instruction_program():
    """Executes every instruction form once, in a safe order, then HLT."""
    lines = ["        LD SP, #$F0", "        LD X, #$9000", "        LD A, #$5A",
             "        LD B, #$A5"]
    for n, ins in enumerate(isa.INSTRS):
        if ins.mnem in ("HLT", "POPF", "RET") or (ins.mnem == "LD" and ins.operands[0] == "SP"):
            continue
        ops = []
        for o in ins.operands:
            ops.append({"imm8": "#$%02X" % ((n * 37) & 0xFF), "imm16": "#$9010",
                        "abs": "[$9020]", "ind": "[X]", "indinc": "[X+]",
                        "addr": "next%d" % n}.get(o, o))
        if ins.mnem in ("JMP", "CALL") and ins.operands == ("X",):
            lines.append("        LD X, #next%d" % n)
        if ins.mnem == "MOV" and ins.operands[0] == "SP":
            lines.append("        LD A, #$F0")
        if ins.mnem == "CALL":
            lines.append("        %s %s" % (ins.mnem, ", ".join(ops) if ins.operands != ("X",) else "X"))
            lines.append("        JMP after%d" % n)
            lines.append("next%d:  PUSHF" % n)
            lines.append("        POPF")
            lines.append("        RET")
            lines.append("after%d: LD X, #$9000" % n)
            continue
        lines.append("        %s %s" % (ins.mnem, ", ".join(ops)))
        lines.append("next%d:" % n)
        if ins.mnem in ("JMP",) or ins.operands and ins.operands[0] in ("X",) or \
                (ins.mnem == "MOV" and ins.operands[0] in ("XL", "XH")):
            lines.append("        LD X, #$9000")
    lines += ["        ST A, [$6005]", "        ST B, [$7123]", "        ST A, [$5004]",
              "        HLT"]
    return "\n".join(lines)


class TestStatic(unittest.TestCase):
    def test_netlist_checks_clean(self):
        self.assertEqual(gatesim.check(DESIGN), [])

    def test_pin_tables(self):
        import lib
        self.assertEqual(lib.check_tables(), [])


class TestCPUInNetlist(unittest.TestCase):
    def test_every_instruction_matches_microcode_cpu(self):
        prog = every_instruction_program()
        flash, a = rom_with(prog)
        b = board(flash)
        self.assertTrue(run_until_halt(b, 6000), "netlist CPU did not reach HLT")
        m = sim.Machine(flash)
        c = sim.MicroCPU(m)
        c.pc, c.step = 0, 0
        c.run(200000)
        st = b.cpu_state()
        self.assertEqual((st["a"], st["b"], st["x"], st["sp"], st["pc"], st["flags"]),
                         (c.a, c.b, c.x, c.sp, c.pc, c.flags))
        self.assertEqual(bytes(b.memory(design.REF_RAM)), bytes(m.sram))
        self.assertEqual(bytes(b.memory(design.REF_VRAM)[:4096]), bytes(m.vram))
        self.assertEqual(bytes(b.memory(design.REF_FONT)[:4096]), bytes(m.font))
        self.assertEqual(b.reg("SCROLL_X") & 0x7F, m.scroll_x)
        self.assertEqual(b.contention, [])

    def test_firmware_boot_matches_for_20000_cycles(self):
        b = board()
        m = sim.Machine(ROMS["firmware"])
        c = sim.MicroCPU(m)
        c.pc, c.step = 0, 0
        ref, gl = [], []
        for _ in range(20000):
            if c.step == 0:
                ref.append((c.pc, c.a, c.b, c.x, c.sp, c.flags))
            c.cycle()
        for _ in range(20001):
            st = b.cpu_state()
            if st["step"] == 0:
                gl.append((st["pc"], st["a"], st["b"], st["x"], st["sp"], st["flags"]))
            b.run_cycles(1)
        gl = gl[1:]
        n = min(len(ref), len(gl))
        self.assertGreater(n, 7000)
        self.assertEqual(gl[:n], ref[:n])
        self.assertEqual(bytes(b.memory(design.REF_RAM)), bytes(m.sram))
        self.assertEqual(b.contention, [])

    def test_write_protection(self):
        prog = """
        LD A, #$77
        ST A, [$B000]           ; allowed: code runs from ROM
        LD X, #code
        LD B, #8
copy:   LD A, [X+]              ; copy the RAM part to $8000
        PUSH X
        LD X, #$8000 - 1
        ...
"""
        # build the RAM routine with the cross-assembler, place it in SRAM directly
        ram_img, _ = asm.assemble("LD A, #$55\nST A, [$B001]\nST A, [$8100]\nHLT", origin=0x8000)
        flash, _ = rom_with("LD A, #$77\nST A, [$B000]\nJMP $8000")
        b = board(flash)
        for addr, v in ram_img.items():
            b.memory(design.REF_RAM)[addr - 0x8000] = v
        self.assertTrue(run_until_halt(b, 400))
        ram = b.memory(design.REF_RAM)
        self.assertEqual(ram[0x3000], 0x77)      # $B000 written from ROM code
        self.assertNotEqual(ram[0x3001], 0x55)   # $B001 blocked: code ran from RAM
        self.assertEqual(ram[0x0100], 0x55)      # $8100 allowed
        self.assertEqual(b.nets["VIOLF"], 1)


class TestClockControl(unittest.TestCase):
    def test_step_mode_and_step_button(self):
        flash, _ = rom_with("loop: INC A\nJMP loop")
        b = board(flash)
        b.run_cycles(20)
        b.set_ext("STEP_MODE", 1)
        b.run_cycles(3)
        pc0, a0 = b.cpu_state()["pc"], b.reg("register A")
        b.run_cycles(50)
        self.assertEqual((b.cpu_state()["pc"], b.reg("register A")), (pc0, a0))
        steps = []
        for _ in range(6):                       # each press = exactly one microinstruction
            s0 = b.cpu_state()["step"]
            b.set_ext("STEPBTN_RC", 0)
            b.run_cycles(4)
            b.set_ext("STEPBTN_RC", 1)
            b.run_cycles(4)
            steps.append((s0, b.cpu_state()["step"]))
        for before, after in steps:
            self.assertIn(after, (0, before + 1))
        self.assertGreater(b.reg("register A"), a0 - 1)

    def test_halt_and_continue(self):
        flash, _ = rom_with("LD A, #1\nHLT\nLD A, #2\nHLT")
        b = board(flash)
        self.assertTrue(run_until_halt(b, 100))
        self.assertEqual(b.reg("register A"), 1)
        b.run_cycles(30)
        self.assertEqual(b.reg("register A"), 1)            # stopped
        b.set_ext("CONTBTN_RC", 0)
        b.run_cycles(3)
        b.set_ext("CONTBTN_RC", 1)
        for _ in range(60):
            b.run_cycles(1)
            if b.reg("register A") == 2:
                break
        self.assertEqual(b.reg("register A"), 2)

    def test_half_speed_jumper(self):
        flash, _ = rom_with("loop: INC A\nJMP loop")
        b = board(flash)
        pc_counts = []
        for half in (0, 1):
            b.set_ext("HALF_EN", half) if "HALF_EN" in b.ext else None
            b.ext["HALF_EN"] = half
            b.nets["HALF_EN"] = half
            b.queue |= b.readers["HALF_EN"]
            b.settle()
            a0 = b.reg("register A")
            b.run_cycles(400)
            pc_counts.append((b.reg("register A") - a0) & 0xFF)
        self.assertAlmostEqual(pc_counts[1] / pc_counts[0], 0.5, delta=0.1)


class TestVideoInNetlist(unittest.TestCase):
    def test_pixels_and_syncs_match_reference(self):
        b = board(rom_with("loop: JMP loop")[0])
        vram, font = b.memory(design.REF_VRAM), b.memory(design.REF_FONT)
        import random
        rng = random.Random(3)
        for i in range(4096):
            vram[i] = rng.randrange(256)
        for i in range(4096):
            font[i] = rng.randrange(256)
        # start just before the end of a frame so vsync comes quickly
        vchips = [b.chips[r] for r, p in b.d.parts.items() if p.note == "V counter"]
        target = 486                            # vsync is on lines 490-491
        for k, ch in enumerate(vchips):
            ch.state["q"] = (target >> (4 * k)) & 15
        b.queue |= set(b.chips)
        b.settle()
        dots = []
        for _ in range(800 * 52):               # vsync, back porch, then 10 visible lines
            b.half_dot()
            b.half_dot()
            dots.append((b.nets["VIDEO"], b.nets["HSQ"], b.nets["VSQ"]))
        hs = [d[1] for d in dots]
        vs = [d[2] for d in dots]
        fall = [i for i in range(1, len(hs)) if hs[i - 1] == 1 and hs[i] == 0]
        self.assertTrue(all(b2 - a2 == 800 for a2, b2 in zip(fall, fall[1:])))
        rise = [i for i in range(1, len(hs)) if hs[i - 1] == 0 and hs[i] == 1]
        self.assertEqual({r - f for f, r in zip(fall, [r for r in rise if r > fall[0]])}, {96})
        vfall = next(i for i in range(1, len(vs)) if vs[i - 1] == 1 and vs[i] == 0)
        first_line = next(k for k, e in enumerate(fall) if e > vfall - 400) + 2 + 33
        ref = video.render(vram, font)
        for y in range(8):
            start = fall[first_line + y] + 96 + 48
            got = [dots[start + x][0] for x in range(640)]
            self.assertEqual(got, ref[y], "line %d" % y)
        self.assertEqual(b.contention, [])


class TestKeyboardAndEEPROM(unittest.TestCase):
    def test_ps2_byte_received_and_keyboard_held(self):
        prog = """
        LD B, #48               ; first wait ~1.5 ms: the byte arrives meanwhile
delay:  LD A, #12
d2:     DEC A
        JNZ d2
        DEC B
        JNZ delay
wait:   LD A, [KBD_STATUS]
        AND A, #1
        JZ wait
        LD A, [KBD_STATUS]
        ST A, [$8001]
        LD A, [KBD_DATA]
        ST A, [$8000]
        HLT
"""
        b = board(rom_with(prog)[0])
        bits = ps2.frame_bits(0x1C)
        held = None
        for bit in bits:                         # 12.5 kHz: 252 CPU cycles per bit
            b.set_ext("KDATA", 0 if bit == 0 else None)
            b.run_cycles(126)
            b.set_ext("KCLK", 0)
            b.run_cycles(126)
            b.set_ext("KCLK", None)
        b.set_ext("KDATA", None)
        held = b.nets["KCLK"]                    # 74HC05 holds the clock low until read
        self.assertEqual(b.nets["KREADY"], 1)
        self.assertTrue(run_until_halt(b, 8000))
        self.assertEqual(held, 0)
        self.assertEqual(b.memory(design.REF_RAM)[0], 0x1C)
        self.assertEqual(b.memory(design.REF_RAM)[1] & 0x0D, 0x09)     # ready, start 0, stop 1
        b.run_cycles(5)
        self.assertEqual(b.nets["KCLK"], 1)      # released after the read

    def test_spi_to_eeprom(self):
        prog = """
        LD A, #4
        ST A, [OUT_PORT]
        LD A, #$06              ; WREN
        CALL frame1
        LD A, #$05              ; RDSR -> $8000
        CALL begin
        CALL spi
        LD A, #0
        CALL spi
        ST A, [$8000]
        CALL end
        HLT
frame1: CALL begin
        CALL spi
        JMP end
begin:  PUSH A
        LD A, #0
        ST A, [OUT_PORT]
        POP A
        RET
end:    LD A, #4
        ST A, [OUT_PORT]
        RET
spi:    LD B, #8                ; send A, receive into A
        ST A, [$8010]
        LD A, #0
        ST A, [$8011]
sl:     LD A, [$8010]
        SHL A
        ST A, [$8010]
        LD A, #0
        JNC s0
        LD A, #2
s0:     ST A, [OUT_PORT]
        OR A, #1
        ST A, [OUT_PORT]
        LD A, [IN_PORT]
        SHR A
        LD A, [$8011]
        ROL A
        ST A, [$8011]
        DEC B
        JNZ sl
        LD A, #0
        ST A, [OUT_PORT]
        LD A, [$8011]
        RET
"""
        b = board(rom_with(prog)[0])
        ee = eeprom.EEPROM25LC512()
        last = [None]

        def hook():
            out = sum(b.nets[n] << i for i, n in enumerate(("EE_SCK", "EE_MOSI", "OUT2")))
            if out != last[0]:
                last[0] = out
                ee.pins(out, b.time)
                b.set_ext("MISO", ee.miso())
        orig = b.half_dot

        def half_dot():
            orig()
            hook()
        b.half_dot = half_dot
        self.assertTrue(run_until_halt(b, 20000))
        self.assertEqual(b.memory(design.REF_RAM)[0], 0x02)            # WEL set by WREN


if __name__ == "__main__":
    unittest.main()
