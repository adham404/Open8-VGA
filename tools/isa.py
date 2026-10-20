"""Open8 ISA: single source of truth for control signals, microcode and encodings.

Everything else (microcode ROM generator, assembler, simulator, ISA doc) imports this.
"""
from alu import OP as ALU

# ---------------------------------------------------------------- control word
# Bus sources (DSRC, bits 0-3) -> 74HC154 #1, one /OE active per microstep
SRC = {n: i for i, n in enumerate(
    ["NONE", "A", "B", "ALU", "MEM", "XL", "XH", "SP", "PCL", "PCH", "FLAGS"])}
# Bus destinations (DDST, bits 4-7) -> 74HC154 #2, one load strobe per microstep
DST = {n: i for i, n in enumerate(
    ["NONE", "A", "B", "T", "L", "IR", "MARL", "MARH", "XL", "XH", "SP", "MEM", "FLAGS"])}
# Address-bus source (ASEL, bits 12-13) -> 74HC139
ASEL = {"PC": 0, "MAR": 1, "X": 2, "SP": 3}

F_SRC_SHIFT, F_DST_SHIFT, F_ALU_SHIFT, F_ASEL_SHIFT = 0, 4, 8, 12
BITS = {
    "PC_INC": 14,     # PC <- PC + 1
    "PC_LOAD": 15,    # PC <- address bus
    "X_INC": 16,      # X <- X + 1
    "FLAGS_ALU": 17,  # FLAGS <- ALU flag ROM output
    "END": 18,        # microstep counter <- 0 (next cycle is a fetch)
    "HALT": 19,       # stop the CPU clock after this cycle
    "PC_CLR": 20,     # PC <- 0
    "TRAP": 21,       # set TRAP status latch
}
STACK_PAGE = 0xAF

C_FLAG, Z_FLAG, N_FLAG, V_FLAG = 1, 2, 4, 8


class U:
    """One microinstruction."""
    __slots__ = ("src", "dst", "alu", "asel", "bits")

    def __init__(self, src="NONE", dst="NONE", alu=0, asel="PC", **bits):
        self.src, self.dst, self.alu, self.asel = src, dst, alu, asel
        for b in bits:
            if b not in BITS:
                raise KeyError(b)
        self.bits = {b for b, v in bits.items() if v}

    def end(self):
        self.bits.add("END")
        return self

    def encode(self):
        w = SRC[self.src] << F_SRC_SHIFT
        w |= DST[self.dst] << F_DST_SHIFT
        w |= (self.alu & 0xF) << F_ALU_SHIFT
        w |= ASEL[self.asel] << F_ASEL_SHIFT
        for b in self.bits:
            w |= 1 << BITS[b]
        return w


def decode(w):
    """Inverse of U.encode (for the simulator / disassembly of microcode)."""
    src = {v: k for k, v in SRC.items()}[(w >> F_SRC_SHIFT) & 0xF]
    dst = {v: k for k, v in DST.items()}[(w >> F_DST_SHIFT) & 0xF]
    asel = {v: k for k, v in ASEL.items()}[(w >> F_ASEL_SHIFT) & 0x3]
    u = U(src, dst, (w >> F_ALU_SHIFT) & 0xF, asel)
    u.bits = {b for b, n in BITS.items() if w >> n & 1}
    return u


FETCH = U(asel="PC", src="MEM", dst="IR", PC_INC=1)


# --------------------------------------------------------------- micro helpers
def imm_to(dst):
    return U(asel="PC", src="MEM", dst=dst, PC_INC=1)


def fetch_addr():
    return [imm_to("MARL"), imm_to("MARH")]


def push(src):
    return [U(src="SP", dst="L"), U(src="ALU", alu=ALU["DEC"], dst="SP"),
            U(asel="SP", src=src, dst="MEM")]


def pop(dst):
    return [U(asel="SP", src="MEM", dst=dst), U(src="SP", dst="L"),
            U(src="ALU", alu=ALU["INC"], dst="SP")]


def ended(seq):
    seq[-1].end()
    return seq


# ------------------------------------------------------------- instructions
class Instr:
    def __init__(self, mnem, operands, size, micro, flags, desc):
        self.mnem = mnem            # e.g. "LD"
        self.operands = operands    # tuple of operand kinds, see assembler
        self.size = size            # bytes including opcode
        self.micro = micro          # f(flags) -> list[U] (steps after fetch)
        self.flags = flags          # text, e.g. "Z N C V" or "-"
        self.desc = desc
        self.opcode = None

    def syntax(self):
        shown = {"imm8": "#n", "imm16": "#nn", "abs": "[addr]", "ind": "[X]",
                 "indinc": "[X+]", "addr": "addr"}
        ops = ", ".join(shown.get(o, o) for o in self.operands)
        return (self.mnem + " " + ops).strip()


INSTRS = []


def I(mnem, operands, size, micro, flags, desc):
    INSTRS.append(Instr(mnem, tuple(operands), size, micro, flags, desc))


# Opcode $00 is HLT so a program that runs into cleared memory stops.
I("HLT", [], 1, lambda f: [U(HALT=1).end()], "-",
  "Stop the CPU clock. CONTINUE resumes at the next instruction; RESET returns to the editor.")
I("NOP", [], 1, lambda f: [U().end()], "-", "Do nothing.")

for r in ("A", "B"):
    I("LD", [r, "imm8"], 2, lambda f, r=r: [imm_to(r).end()], "-", f"{r} <- n")
    I("LD", [r, "abs"], 3, lambda f, r=r: ended(
        fetch_addr() + [U(asel="MAR", src="MEM", dst=r)]), "-", f"{r} <- mem[addr]")
    I("LD", [r, "ind"], 1, lambda f, r=r: [U(asel="X", src="MEM", dst=r).end()], "-",
      f"{r} <- mem[X]")
    I("LD", [r, "indinc"], 1, lambda f, r=r: [U(asel="X", src="MEM", dst=r, X_INC=1).end()],
      "-", f"{r} <- mem[X]; X <- X+1")
    I("ST", [r, "abs"], 3, lambda f, r=r: ended(
        fetch_addr() + [U(asel="MAR", src=r, dst="MEM")]), "-", f"mem[addr] <- {r}")
    I("ST", [r, "ind"], 1, lambda f, r=r: [U(asel="X", src=r, dst="MEM").end()], "-",
      f"mem[X] <- {r}")
    I("ST", [r, "indinc"], 1, lambda f, r=r: [U(asel="X", src=r, dst="MEM", X_INC=1).end()],
      "-", f"mem[X] <- {r}; X <- X+1")

I("LD", ["X", "imm16"], 3, lambda f: [imm_to("XL"), imm_to("XH").end()], "-", "X <- nn")
I("LD", ["SP", "imm8"], 2, lambda f: [imm_to("SP").end()], "-",
  "SP <- n (stack is at $AF00+SP, grows down, SP points at the last pushed byte)")

MOVES = [("A", "B"), ("B", "A"), ("A", "XL"), ("A", "XH"), ("B", "XL"), ("B", "XH"),
         ("XL", "A"), ("XH", "A"), ("XL", "B"), ("XH", "B"), ("A", "SP"), ("SP", "A")]
for d, s in MOVES:
    I("MOV", [d, s], 1, lambda f, d=d, s=s: [U(src=s, dst=d).end()], "-", f"{d} <- {s}")

# Two-operand ALU instructions. op_for(f) picks the ALU op from the current flags.
BINARY = [
    ("ADD", lambda f: ALU["ADD"], True, "A <- A + src"),
    ("ADC", lambda f: ALU["ADD1"] if f & C_FLAG else ALU["ADD"], True, "A <- A + src + C"),
    ("SUB", lambda f: ALU["SUB"], True, "A <- A - src (C = borrow)"),
    ("SBC", lambda f: ALU["SUB1"] if f & C_FLAG else ALU["SUB"], True, "A <- A - src - C"),
    ("AND", lambda f: ALU["AND"], True, "A <- A AND src (C=0, V=0)"),
    ("OR", lambda f: ALU["OR"], True, "A <- A OR src (C=0, V=0)"),
    ("XOR", lambda f: ALU["XOR"], True, "A <- A XOR src (C=0, V=0)"),
    ("CMP", lambda f: ALU["SUB"], False, "flags of A - src; A unchanged (JC = A < src unsigned)"),
]


def _result(op_for, store):
    def mk(f):
        if store:
            return U(src="ALU", dst="A", alu=op_for(f), FLAGS_ALU=1).end()
        return U(alu=op_for(f), FLAGS_ALU=1).end()
    return mk


for name, op_for, store, desc in BINARY:
    res = _result(op_for, store)
    I(name, ["A", "B"], 1, lambda f, res=res: [U(src="A", dst="L"), U(src="B", dst="T"),
                                               res(f)], "Z N C V", desc.replace("src", "B"))
    I(name, ["A", "imm8"], 2, lambda f, res=res: [U(src="A", dst="L"), imm_to("T"), res(f)],
      "Z N C V", desc.replace("src", "n"))
    I(name, ["A", "abs"], 3, lambda f, res=res: fetch_addr() + [
        U(src="A", dst="L"), U(asel="MAR", src="MEM", dst="T"), res(f)],
      "Z N C V", desc.replace("src", "mem[addr]"))
    I(name, ["A", "ind"], 1, lambda f, res=res: [
        U(src="A", dst="L"), U(asel="X", src="MEM", dst="T"), res(f)],
      "Z N C V", desc.replace("src", "mem[X]"))

UNARY = [
    ("NOT", lambda f: ALU["NOT"], "{r} <- NOT {r} (C=0, V=0)"),
    ("SHL", lambda f: ALU["SHL"], "C <- {r}7, {r} <- {r} << 1"),
    ("SHR", lambda f: ALU["SHR"], "C <- {r}0, {r} <- {r} >> 1 (logical)"),
    ("ROL", lambda f: ALU["SHL1"] if f & C_FLAG else ALU["SHL"], "{r} <- {r} << 1 | C, C <- old {r}7"),
    ("ROR", lambda f: ALU["SHR1"] if f & C_FLAG else ALU["SHR"], "{r} <- C << 7 | {r} >> 1, C <- old {r}0"),
    ("INC", lambda f: ALU["INC"], "{r} <- {r} + 1 (C = carry out)"),
    ("DEC", lambda f: ALU["DEC"], "{r} <- {r} - 1 (C = borrow)"),
]
for r in ("A", "B"):
    for name, op_for, desc in UNARY:
        I(name, [r], 1, lambda f, r=r, op_for=op_for: [
            U(src=r, dst="L"), U(src="ALU", dst=r, alu=op_for(f), FLAGS_ALU=1).end()],
          "Z N C V", desc.format(r=r))

I("INC", ["X"], 1, lambda f: [U(X_INC=1).end()], "-", "X <- X + 1 (flags unchanged)")


def _dec_x(f):
    seq = [U(src="XL", dst="L"), U(src="ALU", dst="XL", alu=ALU["DEC"], FLAGS_ALU=1)]
    if f & C_FLAG:   # flags here are the ones just loaded: borrow out of XL
        seq += [U(src="XH", dst="L"), U(src="ALU", dst="XH", alu=ALU["DEC"], FLAGS_ALU=1)]
    else:
        seq += [U()]
    return ended(seq)


I("DEC", ["X"], 1, _dec_x, "C (Z N V undefined)", "X <- X - 1; C = 16-bit borrow")


def _add_x(f):
    seq = [U(src="XL", dst="L"), U(src="A", dst="T"),
           U(src="ALU", dst="XL", alu=ALU["ADD"], FLAGS_ALU=1)]
    if f & C_FLAG:
        seq += [U(src="XH", dst="L"), U(src="ALU", dst="XH", alu=ALU["INC"], FLAGS_ALU=1)]
    else:
        seq += [U()]
    return ended(seq)


I("ADD", ["X", "A"], 1, _add_x, "C (Z N V undefined)", "X <- X + A (A unsigned); C = 16-bit carry")

I("CLC", [], 1, lambda f: [U(src="FLAGS", dst="L"),
                           U(src="ALU", alu=ALU["CLRC"], dst="FLAGS").end()], "C", "C <- 0")
I("SEC", [], 1, lambda f: [U(src="FLAGS", dst="L"),
                           U(src="ALU", alu=ALU["SETC"], dst="FLAGS").end()], "C", "C <- 1")

I("JMP", ["addr"], 3, lambda f: ended(fetch_addr() + [U(asel="MAR", PC_LOAD=1)]), "-",
  "PC <- addr")
I("JMP", ["X"], 1, lambda f: [U(asel="X", PC_LOAD=1).end()], "-", "PC <- X")

CONDS = [("JZ", Z_FLAG, True), ("JNZ", Z_FLAG, False), ("JC", C_FLAG, True),
         ("JNC", C_FLAG, False), ("JN", N_FLAG, True), ("JNN", N_FLAG, False),
         ("JV", V_FLAG, True), ("JNV", V_FLAG, False)]
for name, bit, want in CONDS:
    def _jcc(f, bit=bit, want=want):
        taken = bool(f & bit) == want
        return ended(fetch_addr() + [U(asel="MAR", PC_LOAD=1) if taken else U()])
    flag_name = {C_FLAG: "C", Z_FLAG: "Z", N_FLAG: "N", V_FLAG: "V"}[bit]
    I(name, ["addr"], 3, _jcc, "-", f"if {flag_name}={int(want)}: PC <- addr")

I("CALL", ["addr"], 3, lambda f: ended(fetch_addr() + push("PCH") + push("PCL") +
                                       [U(asel="MAR", PC_LOAD=1)]), "-",
  "push return address (high, then low); PC <- addr")
I("CALL", ["X"], 1, lambda f: ended(push("PCH") + push("PCL") + [U(asel="X", PC_LOAD=1)]),
  "-", "push return address; PC <- X")
I("RET", [], 1, lambda f: ended(pop("MARL") + pop("MARH") + [U(asel="MAR", PC_LOAD=1)]),
  "-", "pop return address; PC <- it")

for r in ("A", "B"):
    I("PUSH", [r], 1, lambda f, r=r: ended(push(r)), "-", f"SP <- SP-1; mem[$AF00+SP] <- {r}")
    I("POP", [r], 1, lambda f, r=r: ended(pop(r)), "-", f"{r} <- mem[$AF00+SP]; SP <- SP+1")
I("PUSH", ["X"], 1, lambda f: ended(push("XH") + push("XL")), "-", "push XH, then XL")
I("POP", ["X"], 1, lambda f: ended(pop("XL") + pop("XH")), "-", "pop XL, then XH")
I("PUSHF", [], 1, lambda f: ended(push("FLAGS")), "-", "push FLAGS (0000VNZC)")
I("POPF", [], 1, lambda f: ended(pop("FLAGS")), "all", "pop FLAGS")


def TRAP_MICRO(f):
    """Executed for every unassigned opcode (including erased-flash $FF)."""
    return ended(push("PCH") + push("PCL") + [U(PC_CLR=1, TRAP=1)])


for i, ins in enumerate(INSTRS):
    ins.opcode = i
assert len(INSTRS) <= 255, len(INSTRS)

BY_OPCODE = {ins.opcode: ins for ins in INSTRS}
