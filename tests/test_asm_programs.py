"""Phase 2: assembler unit tests and whole programs executed on the microcode CPU."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import asm   # noqa: E402
import isa   # noqa: E402
import sim   # noqa: E402

OPC = {}
for _i in isa.INSTRS:
    OPC[_i.syntax()] = _i.opcode


def run(source, max_cycles=2_000_000, kbd=(), from_rom=False):
    """Assemble at $8000 (or $0000 in flash), run on the microcode CPU until HLT."""
    origin = 0x0000 if from_rom else 0x8000
    image, a = asm.assemble(source, origin=origin)
    m = sim.Machine()
    for addr, b in image.items():
        if from_rom:
            m.flash[addr] = b
        else:
            m.sram[addr - 0x8000] = b
    m.kbd = list(kbd)
    cpu = sim.MicroCPU(m)
    cpu.pc = origin
    cpu.sp = 0x00
    halted = cpu.run(max_cycles)
    return cpu, m, a, halted


class TestAssembler(unittest.TestCase):
    def test_every_instruction_form_round_trips(self):
        for ins in isa.INSTRS:
            ops = []
            for o in ins.operands:
                ops.append({"imm8": "#$12", "imm16": "#$1234", "abs": "[$1234]", "ind": "[X]",
                            "indinc": "[X+]", "addr": "$1234"}.get(o, o))
            src = "  %s %s" % (ins.mnem, ", ".join(ops))
            img, _ = asm.assemble(src)
            data = [img[k] for k in sorted(img)]
            self.assertEqual(data[0], ins.opcode, src)
            self.assertEqual(len(data), ins.size, src)
            if ins.size == 2:
                self.assertEqual(data[1], 0x12)
            if ins.size == 3:
                self.assertEqual(data[1:], [0x34, 0x12])

    def test_literals_and_expressions(self):
        src = """
        VAL = 10
        .db 255, $FF, 0xff, %11111111, 0b11111111, 'A', VAL*2+1, <$1234, >$1234
        .dw label, $ - 1
        label: .db "Hi\\n", 0
        .ds 3, $EE
        """
        img, a = asm.assemble(src)
        data = [img[k] for k in sorted(img)]
        self.assertEqual(data[:9], [255] * 5 + [65, 21, 0x34, 0x12])
        self.assertEqual(data[9:11], [0x0D, 0x80])     # label = $800D
        self.assertEqual(data[11:13], [0x08, 0x80])    # $ at .dw = $8009 -> $8008
        self.assertEqual(data[13:17], [ord("H"), ord("i"), 10, 0])
        self.assertEqual(data[17:], [0xEE] * 3)

    def test_forward_reference_and_aliases(self):
        img, a = asm.assemble("JEQ fwd\nJNE fwd\nfwd: HLT")
        self.assertEqual([img[k] for k in sorted(img)],
                         [OPC["JZ addr"], 6, 0x80, OPC["JNZ addr"], 6, 0x80, OPC["HLT"]])

    def assertError(self, src, text, line=None, **kw):
        with self.assertRaises(asm.AsmError) as cm:
            asm.assemble(src, **kw)
        self.assertIn(text, cm.exception.msg)
        if line is not None:
            self.assertEqual(cm.exception.line, line)

    def test_errors_report_line_numbers(self):
        self.assertError("NOP\nFROB A", "unknown instruction", 2)
        self.assertError("NOP\nNOP\nLD A, X", "invalid operands", 3)
        self.assertError("JMP nowhere", "undefined symbol", 1)
        self.assertError("LD A, #300", "does not fit", 1)
        self.assertError("foo: NOP\nfoo: NOP", "defined twice", 2)
        self.assertError("A: NOP", "reserved", 1)
        self.assertError(".ds 17\nNOP", "too large", 2, limit=0x8010)
        self.assertError("LD A, #(1+2", "missing ')'", 1)


class TestPrograms(unittest.TestCase):
    def test_counter_loop(self):
        cpu, m, a, halted = run("""
            LD B, #10
            LD A, #0
        loop: ADD A, #3
            DEC B
            JNZ loop
            ST A, [result]
            HLT
        result: .db 0
        """)
        self.assertTrue(halted)
        self.assertEqual(m.sram[a.symbols["RESULT"] - 0x8000], 30)

    def test_16bit_add_with_carry(self):
        cpu, m, a, _ = run("""
            LD A, [n1]
            ADD A, [n2]
            ST A, [sum]
            LD A, [n1+1]
            ADC A, [n2+1]
            ST A, [sum+1]
            HLT
        n1: .dw 1000
        n2: .dw 60000
        sum: .dw 0
        """)
        s = a.symbols["SUM"] - 0x8000
        self.assertEqual(m.sram[s] | m.sram[s + 1] << 8, 61000)

    def test_multiply_by_shift_and_add(self):
        cpu, m, a, _ = run("""
            ; 8x8 -> 8 bit multiply 13 * 11 = 143 using shift/add
            LD A, #0
            ST A, [res]
            LD A, #13
            ST A, [mcand]
            LD B, #11
        mloop:
            MOV A, B
            JZ done
            SHR B
            JNC skip
            LD A, [res]
            ADD A, [mcand]
            ST A, [res]
        skip:
            LD A, [mcand]
            SHL A
            ST A, [mcand]
            JMP mloop
        done: HLT
        res: .db 0
        mcand: .db 0
        """)
        self.assertEqual(m.sram[a.symbols["RES"] - 0x8000], 143)

    def test_call_ret_stack_and_string_copy(self):
        cpu, m, a, _ = run("""
            LD SP, #0
            LD X, #msg
            CALL strlen
            ST B, [len]
            HLT
        strlen:            ; X -> string, returns length in B
            PUSH A
            LD B, #0
        sl: LD A, [X+]
            CMP A, #0
            JZ sd
            INC B
            JMP sl
        sd: POP A
            RET
        msg: .db "Open8-VGA", 0
        len: .db 0
        """)
        self.assertEqual(m.sram[a.symbols["LEN"] - 0x8000], 9)
        self.assertEqual(cpu.sp, 0)

    def test_write_text_to_vram(self):
        cpu, m, a, _ = run("""
            LD X, #msg
            LD A, #<(VRAM + 2*128 + 5)   ; row 2, column 5
            ST A, [ptr]
            LD A, #>(VRAM + 2*128 + 5)
            ST A, [ptr+1]
        next:
            LD A, [X+]
            CMP A, #0
            JZ done
            PUSH X
            MOV B, A
            LD A, [ptr]
            MOV XL, A
            LD A, [ptr+1]
            MOV XH, A
            ST B, [X+]
            MOV A, XL
            ST A, [ptr]
            MOV A, XH
            ST A, [ptr+1]
            POP X
            JMP next
        done: HLT
        msg: .db "HELLO", 0
        ptr: .dw 0
        """)
        self.assertEqual(bytes(m.vram[2 * 128 + 5: 2 * 128 + 10]), b"HELLO")

    def test_keyboard_poll(self):
        cpu, m, a, _ = run("""
        wait: LD A, [KBD_STATUS]
            AND A, #1
            JZ wait
            LD A, [KBD_DATA]
            ST A, [key]
            HLT
        key: .db 0
        """, kbd=[0x1C])   # scan code for 'A'
        self.assertEqual(m.sram[a.symbols["KEY"] - 0x8000], 0x1C)

    def test_user_code_cannot_write_system_region(self):
        src = """
            LD A, #$55
            ST A, [$B000]
            ST A, [$AEFF]
            HLT
        """
        cpu, m, a, _ = run(src)
        self.assertNotEqual(m.sram[0x3000], 0x55)       # $B000 protected
        self.assertEqual(m.sram[0x2EFF], 0x55)          # $AEFF allowed
        self.assertTrue(m.violation)
        cpu, m, a, _ = run(src, from_rom=True)          # firmware may write anywhere
        self.assertEqual(m.sram[0x3000], 0x55)
        self.assertFalse(m.violation)

    def test_invalid_opcode_traps_to_zero_with_return_address(self):
        image, a = asm.assemble("NOP\n.db $FF\nNOP")
        m = sim.Machine()
        for k, b in image.items():
            m.sram[k - 0x8000] = b
        cpu = sim.MicroCPU(m)
        cpu.pc, cpu.sp = 0x8000, 0
        cpu.step_instr()
        cpu.step_instr()
        self.assertEqual(cpu.pc, 0x0000)
        self.assertTrue(m.trap)
        lo, hi = m.sram[0x2FFE], m.sram[0x2FFF]          # stack at $AFFE/$AFFF
        self.assertEqual(lo | hi << 8, 0x8002)            # address after the bad opcode

    def test_halt_stops(self):
        cpu, m, a, halted = run("HLT")
        self.assertTrue(halted)
        self.assertEqual(cpu.pc, 0x8001)


if __name__ == "__main__":
    unittest.main()
