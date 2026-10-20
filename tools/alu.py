"""Open8 lookup-table ALU: reference semantics and ROM image generation.

ROM address (19 bits) = (L << 11) | (T << 3) | (op & 7)
Ops 0-7 live in the *_0 chips, ops 8-15 in the *_1 chips (op bit 3 picks the chip).
Result ROMs hold the 8-bit result; flag ROMs hold 0000VNZC.
"""
import os
import sys

C_BIT, Z_BIT, N_BIT, V_BIT = 1, 2, 4, 8

OPS = [
    "ADD", "ADD1", "SUB", "SUB1", "AND", "OR", "XOR", "NOT",
    "SHL", "SHR", "SHL1", "SHR1", "INC", "DEC", "CLRC", "SETC",
]
OP = {name: i for i, name in enumerate(OPS)}


def alu(op, l, t):
    """Return (result, flags) for one ALU operation. flags = 0000VNZC.

    Carry convention: for add-type ops C = carry out; for subtract-type ops
    C = borrow (1 when the unsigned result went below zero), as on the Z80/x86.
    """
    c = v = 0
    if op in (0, 1):                       # ADD, ADD+1
        s = l + t + (op & 1)
        r = s & 0xFF
        c = s > 0xFF
        v = (~(l ^ t) & (l ^ r) & 0x80) != 0
    elif op in (2, 3):                     # SUB, SUB-1
        s = l - t - (op & 1)
        r = s & 0xFF
        c = s < 0
        v = ((l ^ t) & (l ^ r) & 0x80) != 0
    elif op == 4:
        r = l & t
    elif op == 5:
        r = l | t
    elif op == 6:
        r = l ^ t
    elif op == 7:
        r = ~l & 0xFF
    elif op in (8, 10):                    # SHL, SHL with bit0 <- 1 (ROL when C=1)
        r = ((l << 1) & 0xFF) | (1 if op == 10 else 0)
        c = l >> 7
    elif op in (9, 11):                    # SHR, SHR with bit7 <- 1 (ROR when C=1)
        r = (l >> 1) | (0x80 if op == 11 else 0)
        c = l & 1
    elif op == 12:                         # INC
        r = (l + 1) & 0xFF
        c = l == 0xFF
        v = l == 0x7F
    elif op == 13:                         # DEC (C = borrow)
        r = (l - 1) & 0xFF
        c = l == 0x00
        v = l == 0x80
    elif op == 14:                         # CLRC: used on the FLAGS byte
        r = l & 0xFE
    elif op == 15:                         # SETC
        r = l | 0x01
    else:
        raise ValueError(op)
    flags = (C_BIT if c else 0) | (Z_BIT if r == 0 else 0) | \
            (N_BIT if r & 0x80 else 0) | (V_BIT if v else 0)
    return r, flags


def rom_address(op, l, t):
    return (l << 11) | (t << 3) | (op & 7)


def build_images():
    """Return dict name -> bytearray(512 KiB) for R0, R1, F0, F1."""
    imgs = {n: bytearray(1 << 19) for n in ("alu_r0", "alu_r1", "alu_f0", "alu_f1")}
    for op in range(16):
        r_img = imgs["alu_r1" if op & 8 else "alu_r0"]
        f_img = imgs["alu_f1" if op & 8 else "alu_f0"]
        for l in range(256):
            for t in range(256):
                r, f = alu(op, l, t)
                a = rom_address(op, l, t)
                r_img[a] = r
                f_img[a] = f
    return imgs


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name, img in build_images().items():
        with open(os.path.join(out_dir, name + ".bin"), "wb") as f:
            f.write(img)
        print("wrote", name + ".bin", len(img), "bytes (SST39SF040)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/rom")
