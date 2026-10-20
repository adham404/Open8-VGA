"""Phase 2 CPU verification: ALU ROM, microcode rules, microcode-vs-reference differential."""
import copy
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import alu      # noqa: E402
import isa      # noqa: E402
import microcode  # noqa: E402
import sim      # noqa: E402

TRIALS = int(os.environ.get("OPEN8_TRIALS", "150"))


class TestALU(unittest.TestCase):
    def test_rom_matches_reference_exhaustively(self):
        imgs = alu.build_images()
        for op in range(16):
            r_img = imgs["alu_r1" if op & 8 else "alu_r0"]
            f_img = imgs["alu_f1" if op & 8 else "alu_f0"]
            for l in range(256):
                for t in range(256):
                    a = alu.rom_address(op, l, t)
                    self.assertEqual((r_img[a], f_img[a]), alu.alu(op, l, t))

    def test_semantics_independent(self):
        """Exhaustive check of alu.alu against a second, differently written model."""
        def flags(r, c=False, v=False):
            return (c and 1) | (r == 0 and 2) | (r >= 128 and 4) | (v and 8)

        def signed(x):
            return x - 256 if x >= 128 else x

        def expect(op, l, t):
            if op in (0, 1):
                full = l + t + op
                r = full % 256
                return r, flags(r, full >= 256, not -128 <= signed(l) + signed(t) + op <= 127)
            if op in (2, 3):
                full = l - t - (op - 2)
                r = full % 256
                return r, flags(r, full < 0, not -128 <= signed(l) - signed(t) - (op - 2) <= 127)
            if op == 4: r = l & t; return r, flags(r)
            if op == 5: r = l | t; return r, flags(r)
            if op == 6: r = l ^ t; return r, flags(r)
            if op == 7: r = 255 - l; return r, flags(r)
            if op in (8, 10): r = (l * 2) % 256 + (op == 10); return r, flags(r, l >= 128)
            if op in (9, 11): r = l // 2 + 128 * (op == 11); return r, flags(r, l % 2 == 1)
            if op == 12: r = (l + 1) % 256; return r, flags(r, l == 255, signed(l) + 1 > 127)
            if op == 13: r = (l - 1) % 256; return r, flags(r, l == 0, signed(l) - 1 < -128)
            if op == 14: r = l - (l % 2); return r, flags(r)
            r = l | 1
            return r, flags(r)

        for op in range(16):
            for l in range(256):
                for t in range(256):
                    self.assertEqual(alu.alu(op, l, t), expect(op, l, t), (alu.OPS[op], l, t))

    def test_spot_values(self):
        self.assertEqual(alu.alu(alu.OP["ADD"], 0xFF, 0x01), (0x00, alu.C_BIT | alu.Z_BIT))
        self.assertEqual(alu.alu(alu.OP["SUB"], 0x00, 0x01), (0xFF, alu.C_BIT | alu.N_BIT))
        self.assertEqual(alu.alu(alu.OP["ADD"], 0x7F, 0x01), (0x80, alu.N_BIT | alu.V_BIT))
        self.assertEqual(alu.alu(alu.OP["SHR"], 0x01, 0)[1], alu.C_BIT | alu.Z_BIT)


class TestMicrocodeRules(unittest.TestCase):
    def test_table_builds_and_validates(self):
        table = microcode.build_table()
        self.assertEqual(len(table), 65536)

    def test_validator_rejects_contention(self):
        bad = [isa.U(src="A", dst="NONE"), isa.U(dst="A"), isa.U(src="MEM", dst="MEM"),
               isa.U(PC_INC=1, PC_LOAD=1, asel="MAR"), isa.U(asel="PC", PC_LOAD=1),
               isa.U(src="ALU", dst="FLAGS", FLAGS_ALU=1), isa.U(src="A", dst="XL", X_INC=1)]
        rejected = 0
        for u in bad:
            try:
                microcode.check_uinstr(u, (0, "t", 1, 0))
            except microcode.MicrocodeError:
                rejected += 1
        # the first one (source with no destination) is legal: CMP-style
        self.assertEqual(rejected, len(bad) - 1)

    def test_all_sequences_fit(self):
        for op in range(256):
            lo, hi = microcode.cycle_counts(op)
            self.assertLessEqual(hi, 16)
            self.assertGreaterEqual(lo, 2)


def random_machine(rng):
    m = sim.Machine(bytes(rng.getrandbits(8) for _ in range(sim.ROM_SIZE)))
    m.sram = bytearray(rng.getrandbits(8) for _ in range(0x8000))
    m.vram = bytearray(rng.getrandbits(8) for _ in range(0x1000))
    m.font = bytearray(rng.getrandbits(8) for _ in range(0x1000))
    m.bank = rng.randrange(32)
    m.kbd = [rng.getrandbits(8) for _ in range(rng.randrange(3))]
    return m


def machine_state(m):
    return (bytes(m.sram), bytes(m.vram), bytes(m.font), m.bank, m.scroll_x, m.scroll_y,
            m.out_port, tuple(m.kbd), m.trap, m.violation)


class TestDifferential(unittest.TestCase):
    """Every opcode (defined or not) x random state: microcode CPU == reference CPU."""

    @classmethod
    def setUpClass(cls):
        sim.roms()   # build once

    def test_every_opcode(self):
        rng = random.Random(1234)
        base = random_machine(rng)
        failures = []
        for op in range(256):
            for trial in range(TRIALS):
                m1 = copy.deepcopy(base)
                m1.kbd = [rng.getrandbits(8) for _ in range(rng.randrange(3))]
                in_rom = rng.random() < 0.3
                pc = rng.randrange(0x0000, 0x3FF0) if in_rom else rng.randrange(0x8000, 0xFFF0)
                code = [op, rng.getrandbits(8), rng.getrandbits(8)]
                for i, b in enumerate(code):
                    if in_rom:
                        m1.flash[pc + i] = b
                    else:
                        m1.sram[pc + i - 0x8000] = b
                m2 = copy.deepcopy(m1)
                regs = dict(a=rng.getrandbits(8), b=rng.getrandbits(8), x=rng.getrandbits(16),
                            sp=rng.getrandbits(8), flags=rng.getrandbits(4), pc=pc)
                mc, rc = sim.MicroCPU(m1), sim.RefCPU(m2)
                mc.load_state(**regs)
                rc.load_state(**regs)
                mc.step_instr()
                rc.step_instr()
                s1, s2 = mc.snapshot(), rc.snapshot()
                mask = ~sim.RefCPU.UNDEFINED_FLAGS.get(op, 0) & 0xF
                s1["flags"] &= mask
                s2["flags"] &= mask
                if s1 != s2 or machine_state(m1) != machine_state(m2):
                    name = isa.BY_OPCODE[op].syntax() if op in isa.BY_OPCODE else "TRAP"
                    failures.append("%02X %s regs=%s micro=%s ref=%s" % (op, name, regs, s1, s2))
                    break
        self.assertEqual(failures, [], "\n".join(failures[:10]))


if __name__ == "__main__":
    unittest.main()
