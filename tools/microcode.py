"""Generate and validate the Open8 microcode ROMs.

Microcode address (16 bits) = IR[7:0] << 8 | STEP[3:0] << 4 | V N Z C
Word (24 bits) is split across three SST39SF010A: ucode0 = bits 0-7, ucode1 = 8-15,
ucode2 = 16-23. The 64 K table is written twice (upper half = jumper bank 1).
"""
import os
import sys

import isa
from isa import U, FETCH

MAX_STEPS = 16


class MicrocodeError(Exception):
    pass


def check_uinstr(u, where):
    errs = []
    if u.dst != "NONE" and u.src == "NONE":
        errs.append("bus destination with no bus source")
    if u.src == "MEM" and u.dst == "MEM":
        errs.append("memory to memory in one cycle")
    if u.src != "NONE" and u.src == u.dst:
        errs.append("register copied onto itself")
    if len({"PC_INC", "PC_LOAD", "PC_CLR"} & u.bits) > 1:
        errs.append("more than one of PC_INC / PC_LOAD / PC_CLR")
    if "PC_LOAD" in u.bits and u.asel == "PC":
        errs.append("PC_LOAD from the PC itself")
    if "FLAGS_ALU" in u.bits and u.dst == "FLAGS":
        errs.append("FLAGS loaded from ALU and bus at once")
    if "X_INC" in u.bits and u.dst in ("XL", "XH"):
        errs.append("X_INC while loading X")
    if u.dst == "IR" and where[2] != 0:
        errs.append("IR loaded outside step 0")
    if u.src in ("MEM",) and u.asel == "SP" and u.dst == "SP":
        errs.append("SP loaded from the stack slot it addresses")
    if errs:
        raise MicrocodeError("%s: %s" % (where, "; ".join(errs)))


def sequence(opcode, flags):
    ins = isa.BY_OPCODE.get(opcode)
    seq = ins.micro(flags) if ins else isa.TRAP_MICRO(flags)
    return [FETCH] + seq


def build_table():
    """Return list of 65536 24-bit words, after validating every sequence."""
    table = [0] * (1 << 16)
    for op in range(256):
        for f in range(16):
            seq = sequence(op, f)
            name = isa.BY_OPCODE[op].syntax() if op in isa.BY_OPCODE else "TRAP"
            if len(seq) > MAX_STEPS:
                raise MicrocodeError("%02X %s flags=%X: %d steps > 16" % (op, name, f, len(seq)))
            ends = [i for i, u in enumerate(seq) if "END" in u.bits]
            if ends != [len(seq) - 1]:
                raise MicrocodeError("%02X %s flags=%X: END must be on the last step only"
                                     % (op, name, f))
            for step, u in enumerate(seq):
                check_uinstr(u, (op, name, step, f))
            for step in range(MAX_STEPS):
                u = seq[step] if step < len(seq) else U().end()   # unreachable filler
                table[(op << 8) | (step << 4) | f] = u.encode()
    # Step 0 must be identical for every IR/flags value: IR still holds the
    # previous opcode during the fetch cycle.
    fetch = FETCH.encode()
    for op in range(256):
        for f in range(16):
            if table[(op << 8) | f] != fetch:
                raise MicrocodeError("step 0 differs at opcode %02X flags %X" % (op, f))
    return table


def cycle_counts(opcode):
    """(min, max) cycles over the 16 starting flag values (fetch included).

    Note: for instructions that change flags mid-way (DEC X, ADD X,A) the real path
    depends on intermediate flags; the simulator reports exact counts.
    """
    lens = [len(sequence(opcode, f)) for f in range(16)]
    return min(lens), max(lens)


def build_images(table):
    imgs = []
    for k in range(3):
        img = bytearray(1 << 17)
        for a, w in enumerate(table):
            b = (w >> (8 * k)) & 0xFF
            img[a] = b
            img[a + (1 << 16)] = b
        imgs.append(img)
    return imgs


def main(out_dir):
    table = build_table()
    os.makedirs(out_dir, exist_ok=True)
    for k, img in enumerate(build_images(table)):
        path = os.path.join(out_dir, "ucode%d.bin" % k)
        with open(path, "wb") as f:
            f.write(img)
        print("wrote", path, len(img), "bytes (SST39SF010A)")
    print("microcode OK: %d opcodes defined, %d trap to $0000"
          % (len(isa.INSTRS), 256 - len(isa.INSTRS)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/rom")
