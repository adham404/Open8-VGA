"""Open8 simulators.

* Machine  - memory map, I/O registers, write protection (shared by both CPUs).
* MicroCPU - cycle-accurate model that executes the *generated microcode and ALU ROM
             bytes*, one control word per clock, exactly as the hardware decodes them.
* RefCPU   - independent instruction-level model written from the ISA spec.
Tests run both on the same inputs and require identical results.
"""
import isa
import alu as alu_mod
import microcode

ROM_SIZE = 1 << 17
SRAM_BASE, PROTECT_BASE = 0x8000, 0xB000


class Machine:
    def __init__(self, flash=None):
        self.flash = bytearray(flash or bytes([0xFF]) * ROM_SIZE)
        self.flash.extend(b"\xff" * (ROM_SIZE - len(self.flash)))
        self.sram = bytearray(0x8000)
        self.vram = bytearray(0x1000)
        self.font = bytearray(0x1000)
        self.bank = 0
        self.scroll_x = self.scroll_y = 0
        self.out_port = 0
        self.in_port = 0xFF        # expansion inputs and MISO have pull-ups
        self.kbd = []              # simple model: pending bytes (used when no PS/2 model attached)
        self.ps2 = None            # ps2.Receiver, attached by system.System
        self.keyboard = None       # ps2.Keyboard
        self.now = 0               # CPU cycle counter, maintained by system.System
        self.eeprom = None         # eeprom.EEPROM25LC512 on the SPI port, if fitted
        self.vblank = False
        self.trap = False
        self.violation = False
        self.writes = []           # log of (addr, value) actually performed

    # ---- bus
    def read(self, a):
        a &= 0xFFFF
        if a < 0x4000:
            return self.flash[a]
        if a < 0x5000:
            return self.flash[(self.bank << 12) | (a & 0xFFF)]
        if a < 0x6000:
            return self.io_read(a & 7)
        if a < 0x7000:
            return self.vram[a & 0xFFF]
        if a < 0x8000:
            return self.font[a & 0xFFF]
        return self.sram[a - SRAM_BASE]

    def write(self, a, v, from_ram):
        a &= 0xFFFF
        v &= 0xFF
        if a < 0x5000:
            return                                  # flash: writes ignored
        if a < 0x6000:
            self.io_write(a & 7, v)
        elif a < 0x7000:
            self.vram[a & 0xFFF] = v
        elif a < 0x8000:
            self.font[a & 0xFFF] = v
        elif from_ram and a >= PROTECT_BASE:
            self.violation = True                   # suppressed by hardware
            return
        else:
            self.sram[a - SRAM_BASE] = v
        self.writes.append((a, v))

    def io_read(self, r):
        if self.ps2 is not None and r in (0, 1):
            self.keyboard.advance(self.now)
            return self.ps2.read_data() if r == 0 else self.ps2.status(self.now)
        if r == 0:
            return self.kbd.pop(0) if self.kbd else 0
        if r == 1:
            return 1 if self.kbd else 0
        if r == 2:
            v = (1 if self.vblank else 0) | (2 if self.trap else 0) | (4 if self.violation else 0)
            self.vblank = False
            return v
        if r == 7:
            if self.eeprom is not None:
                return (self.in_port & 0xFE) | self.eeprom.miso()
            return self.in_port
        return 0xFF                                 # write-only registers float high

    def io_write(self, r, v):
        if r == 2:
            self.trap = self.violation = False
        elif r == 3:
            self.bank = v & 0x1F
        elif r == 4:
            self.scroll_x = v & 0x7F
        elif r == 5:
            self.scroll_y = v & 0x1F
        elif r == 6:
            self.out_port = v
            if self.eeprom is not None:
                self.eeprom.pins(v, self.now)


class CPUState:
    REGS = ("a", "b", "x", "sp", "pc", "flags")

    def __init__(self, m):
        self.m = m
        self.a = self.b = self.sp = self.flags = 0
        self.x = self.pc = 0
        self.halted = False
        self.from_ram = False

    def snapshot(self):
        return {r: getattr(self, r) for r in self.REGS + ("halted",)}

    def load_state(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


_ROM_CACHE = {}


def roms():
    if not _ROM_CACHE:
        table = microcode.build_table()
        _ROM_CACHE["ucode"] = [isa.decode(w) for w in table]
        _ROM_CACHE["alu"] = alu_mod.build_images()
    return _ROM_CACHE["ucode"], _ROM_CACHE["alu"]


class MicroCPU(CPUState):
    def __init__(self, m):
        super().__init__(m)
        self.ucode, imgs = roms()
        self.alu_r = (imgs["alu_r0"], imgs["alu_r1"])
        self.alu_f = (imgs["alu_f0"], imgs["alu_f1"])
        self.ir = 0
        self.step = 0
        self.l = self.t = 0
        self.mar = 0
        self.cycles = 0

    def reset(self):
        self.pc = 0
        self.step = 0
        self.halted = False
        self.m.trap = self.m.violation = False

    def cycle(self):
        u = self.ucode[(self.ir << 8) | (self.step << 4) | self.flags]
        addr = {"PC": self.pc, "MAR": self.mar, "X": self.x,
                "SP": (isa.STACK_PAGE << 8) | self.sp}[u.asel]
        ra = alu_mod.rom_address(u.alu, self.l, self.t)
        alu_result = self.alu_r[u.alu >> 3][ra]
        alu_flags = self.alu_f[u.alu >> 3][ra]
        src = u.src
        if src == "NONE":
            bus = None
        elif src == "MEM":
            bus = self.m.read(addr)
        else:
            bus = {"A": self.a, "B": self.b, "ALU": alu_result, "XL": self.x & 0xFF,
                   "XH": self.x >> 8, "SP": self.sp, "PCL": self.pc & 0xFF,
                   "PCH": self.pc >> 8, "FLAGS": self.flags}[src]
        # ---- clock edge: everything below happens simultaneously
        bits = u.bits
        d = u.dst
        if d == "MEM":
            self.m.write(addr, bus, self.from_ram)
        elif d == "A": self.a = bus
        elif d == "B": self.b = bus
        elif d == "T": self.t = bus
        elif d == "L": self.l = bus
        elif d == "IR":
            self.ir = bus
            self.from_ram = bool(addr & 0x8000)
        elif d == "MARL": self.mar = (self.mar & 0xFF00) | bus
        elif d == "MARH": self.mar = (self.mar & 0x00FF) | (bus << 8)
        elif d == "XL": self.x = (self.x & 0xFF00) | bus
        elif d == "XH": self.x = (self.x & 0x00FF) | (bus << 8)
        elif d == "SP": self.sp = bus
        elif d == "FLAGS": self.flags = bus & 0x0F
        if "PC_INC" in bits: self.pc = (self.pc + 1) & 0xFFFF
        if "PC_LOAD" in bits: self.pc = addr
        if "PC_CLR" in bits: self.pc = 0
        if "X_INC" in bits: self.x = (self.x + 1) & 0xFFFF
        if "FLAGS_ALU" in bits: self.flags = alu_flags
        if "TRAP" in bits: self.m.trap = True
        if "HALT" in bits: self.halted = True
        self.step = 0 if "END" in bits else (self.step + 1) & 0xF
        self.cycles += 1

    def step_instr(self):
        """Run until the end of one instruction. Returns cycles used."""
        start = self.cycles
        self.cycle()
        while self.step != 0:
            self.cycle()
        return self.cycles - start

    def run(self, max_cycles=1_000_000):
        while not self.halted and self.cycles < max_cycles:
            self.step_instr()
        return self.halted


class RefCPU(CPUState):
    """Instruction-level reference model. Written from docs, independent of microcode."""
    UNDEFINED_FLAGS = {}   # opcode -> mask of flags the spec leaves undefined

    def fetch8(self):
        v = self.m.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch8()
        return lo | (self.fetch8() << 8)

    def push(self, v):
        self.sp = (self.sp - 1) & 0xFF
        self.m.write((isa.STACK_PAGE << 8) | self.sp, v, self.from_ram)

    def pop(self):
        v = self.m.read((isa.STACK_PAGE << 8) | self.sp)
        self.sp = (self.sp + 1) & 0xFF
        return v

    def set_zn(self, r, c=0, v=0):
        self.flags = (1 if c else 0) | (2 if r == 0 else 0) | (4 if r & 0x80 else 0) | (8 if v else 0)

    def get(self, name):
        return {"A": self.a, "B": self.b, "XL": self.x & 0xFF, "XH": self.x >> 8,
                "SP": self.sp}[name]

    def put(self, name, v):
        v &= 0xFF
        if name == "A": self.a = v
        elif name == "B": self.b = v
        elif name == "XL": self.x = (self.x & 0xFF00) | v
        elif name == "XH": self.x = (self.x & 0x00FF) | (v << 8)
        elif name == "SP": self.sp = v

    def step_instr(self):
        at = self.pc
        op = self.fetch8()
        self.from_ram = bool(at & 0x8000)
        ins = isa.BY_OPCODE.get(op)
        if ins is None:
            self.push(self.pc >> 8)
            self.push(self.pc & 0xFF)
            self.pc = 0
            self.m.trap = True
            return
        mn, ops = ins.mnem, ins.operands
        c_in = self.flags & 1

        def operand():
            kind = ops[1]
            if kind == "imm8": return self.fetch8()
            if kind == "abs": return self.m.read(self.fetch16())
            if kind == "ind": return self.m.read(self.x)
            if kind == "B": return self.b
            raise AssertionError(kind)

        if mn == "HLT":
            self.halted = True
        elif mn == "NOP":
            pass
        elif mn == "LD" and ops[0] in ("A", "B"):
            kind = ops[1]
            if kind == "imm8": v = self.fetch8()
            elif kind == "abs": v = self.m.read(self.fetch16())
            else:
                v = self.m.read(self.x)
                if kind == "indinc": self.x = (self.x + 1) & 0xFFFF
            self.put(ops[0], v)
        elif mn == "LD" and ops[0] == "X":
            self.x = self.fetch16()
        elif mn == "LD" and ops[0] == "SP":
            self.sp = self.fetch8()
        elif mn == "ST":
            kind = ops[1]
            v = self.get(ops[0])
            if kind == "abs":
                self.m.write(self.fetch16(), v, self.from_ram)
            else:
                self.m.write(self.x, v, self.from_ram)
                if kind == "indinc": self.x = (self.x + 1) & 0xFFFF
        elif mn == "MOV":
            self.put(ops[0], self.get(ops[1]))
        elif mn == "ADD" and ops[0] == "X":
            s = self.x + self.a
            self.x = s & 0xFFFF
            self.flags = (self.flags & ~1) | (1 if s > 0xFFFF else 0)
        elif mn in ("ADD", "ADC"):
            b = operand()
            a = self.a
            s = a + b + (c_in if mn == "ADC" else 0)
            r = s & 0xFF
            self.set_zn(r, s > 0xFF, (a ^ r) & (b ^ r) & 0x80)
            self.a = r
        elif mn in ("SUB", "SBC", "CMP"):
            b = operand()
            a = self.a
            s = a - b - (c_in if mn == "SBC" else 0)
            r = s & 0xFF
            self.set_zn(r, s < 0, (a ^ b) & (a ^ r) & 0x80)
            if mn != "CMP":
                self.a = r
        elif mn in ("AND", "OR", "XOR"):
            b = operand()
            r = {"AND": self.a & b, "OR": self.a | b, "XOR": self.a ^ b}[mn]
            self.set_zn(r)
            self.a = r
        elif mn in ("NOT", "SHL", "SHR", "ROL", "ROR", "INC", "DEC") and ops[0] in ("A", "B"):
            v = self.get(ops[0])
            c = ov = 0
            if mn == "NOT": r = ~v & 0xFF
            elif mn == "SHL": r, c = (v << 1) & 0xFF, v >> 7
            elif mn == "SHR": r, c = v >> 1, v & 1
            elif mn == "ROL": r, c = ((v << 1) & 0xFF) | c_in, v >> 7
            elif mn == "ROR": r, c = (v >> 1) | (c_in << 7), v & 1
            elif mn == "INC": r, c, ov = (v + 1) & 0xFF, v == 0xFF, v == 0x7F
            else: r, c, ov = (v - 1) & 0xFF, v == 0, v == 0x80
            self.set_zn(r, c, ov)
            self.put(ops[0], r)
        elif mn == "INC" and ops[0] == "X":
            self.x = (self.x + 1) & 0xFFFF
        elif mn == "DEC" and ops[0] == "X":
            borrow = self.x == 0
            self.x = (self.x - 1) & 0xFFFF
            self.flags = (self.flags & ~1) | (1 if borrow else 0)
        elif mn == "CLC":
            self.flags &= ~1
        elif mn == "SEC":
            self.flags |= 1
        elif mn == "JMP":
            self.pc = self.x if ops[0] == "X" else self.fetch16()
        elif mn in ("JZ", "JNZ", "JC", "JNC", "JN", "JNN", "JV", "JNV"):
            target = self.fetch16()
            bit = {"Z": 2, "C": 1, "N": 4, "V": 8}[mn[-1]]
            want = mn == "JN" or not mn.startswith("JN")
            if bool(self.flags & bit) == want:
                self.pc = target
        elif mn == "CALL":
            target = self.x if ops[0] == "X" else self.fetch16()
            self.push(self.pc >> 8)
            self.push(self.pc & 0xFF)
            self.pc = target
        elif mn == "RET":
            lo = self.pop()
            self.pc = lo | (self.pop() << 8)
        elif mn == "PUSH":
            if ops[0] == "X":
                self.push(self.x >> 8)
                self.push(self.x & 0xFF)
            else:
                self.push(self.get(ops[0]))
        elif mn == "POP":
            if ops[0] == "X":
                lo = self.pop()
                self.x = lo | (self.pop() << 8)
            else:
                self.put(ops[0], self.pop())
        elif mn == "PUSHF":
            self.push(self.flags)
        elif mn == "POPF":
            self.flags = self.pop() & 0x0F
        else:
            raise NotImplementedError(ins.syntax())

    def run(self, max_instr=200_000):
        n = 0
        while not self.halted and n < max_instr:
            self.step_instr()
            n += 1
        return self.halted


# Flags the ISA leaves undefined (Z N V after DEC X / ADD X,A).
for _ins in isa.INSTRS:
    if _ins.flags.startswith("C (Z N V undefined)"):
        RefCPU.UNDEFINED_FLAGS[_ins.opcode] = 0b1110
