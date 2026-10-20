"""Generate docs/02-isa.md from tools/isa.py (so the spec can never drift from the hardware)."""
import sys

import isa
import microcode

HEADER = """# Open8 Instruction Set (generated — do not edit; run `python3 tools/gendoc.py`)

Author: Adham Elshafei <adham_mohsen@outlook.com>

## Programmer's model
| Register | Width | Notes |
|---|---|---|
| A | 8 | accumulator; destination of all two-operand ALU instructions |
| B | 8 | general purpose; ALU second operand, loop counter |
| X | 16 | index/pointer (`[X]`, `[X+]` post-increment), also `JMP X` / `CALL X` |
| SP | 8 | stack pointer; stack lives at `$AF00 + SP`, grows down, points at last pushed byte |
| PC | 16 | program counter; reset value `$0000` |
| FLAGS | 4 | `0000VNZC` — C carry/borrow, Z zero, N negative (bit 7), V signed overflow |

Carry convention: after ADD/ADC C = carry out; after SUB/SBC/CMP C = **borrow**
(so after `CMP A, n`: `JC` = A < n unsigned, `JZ` = equal, `JNC` = A >= n).
Loads, stores, moves, jumps and stack operations do not change flags.

## Assembly syntax
```
label:  MNEMONIC operand, operand   ; comment
NAME = expression                    ; constant (also: NAME .equ expression)
```
* Operands: `A B X SP XL XH` registers · `#expr` immediate · `[expr]` memory at address ·
  `[X]` memory at X · `[X+]` memory at X then X+1 · `expr` jump/call target.
* Numbers: `42` decimal · `$2A` or `0x2A` hex · `%101010` or `0b101010` binary · `'*'` character.
* Expressions: `+ - * / % & | ^ ~`, parentheses, `<expr` low byte, `>expr` high byte, `$` current address.
* Directives: `.org addr` · `.db 1, 2, "text", 0` · `.dw word, ...` · `.ds count[, fill]`.
* Aliases: `JEQ`=JZ, `JNE`=JNZ, `JLO`=JC, `JHS`=JNC, `JMI`=JN, `JPL`=JNN.
* Mnemonics, registers and symbols are case-insensitive. User programs start at `$8000`.
* Predefined symbols: `KBD_DATA KBD_STATUS SYS_STATUS ROM_BANK SCROLL_X SCROLL_Y OUT_PORT
  IN_PORT VRAM FONT USER_START USER_END STACK_PAGE` (see the memory map).

## Machine code format
One opcode byte, followed by 0, 1 or 2 operand bytes. 16-bit operands are little-endian
(low byte first). Every opcode not listed below (including `$FF`, erased flash) is
**invalid**: it pushes the address after the opcode and jumps to `$0000` with the TRAP
status bit set; the firmware reports "invalid opcode at …" and returns to the editor.

## Instructions
Cycles include the 1-cycle fetch; at 3.147 MHz one cycle = 318 ns.
A range (e.g. 4–5) means the count depends on flags.

| Opcode | Syntax | Bytes | Cycles | Flags | Operation |
|---|---|---|---|---|---|
"""

FOOTER = """
## Microinstruction format (24 bits, 3 × SST39SF010A)
| Bits | Field | Values |
|---|---|---|
| 3–0 | DSRC (bus source) | %s |
| 7–4 | DDST (bus destination) | %s |
| 11–8 | ALUOP | %s |
| 13–12 | ASEL (address source) | %s |
%s
Microcode address = `IR[7:0] STEP[3:0] V N Z C`. Step 0 of every opcode is the fetch
`MEM[PC] -> IR, PC+1`. `END` resets the step counter so the next cycle is a fetch.
Validation rules (enforced by `tools/microcode.py`): one source and one destination per
step by construction; a destination needs a source; no memory-to-memory; at most one of
PC_INC/PC_LOAD/PC_CLR; no PC_LOAD from PC; no FLAGS from ALU and bus together; no X_INC
while loading X; IR loads only in step 0; every sequence ends with END within 16 steps.
"""


def main(path):
    import alu
    rows = []
    for ins in isa.INSTRS:
        lo, hi = microcode.cycle_counts(ins.opcode)
        cyc = str(lo) if lo == hi else "%d–%d" % (lo, hi)
        rows.append("| `$%02X` | `%s` | %d | %s | %s | %s |" % (
            ins.opcode, ins.syntax(), ins.size, cyc, ins.flags, ins.desc.replace("|", "\\|")))
    bits = "\n".join("| %d | %s | 1 = active |" % (n, b) for b, n in sorted(isa.BITS.items(), key=lambda kv: kv[1]))
    footer = FOOTER % (", ".join("%d %s" % (v, k) for k, v in isa.SRC.items()),
                       ", ".join("%d %s" % (v, k) for k, v in isa.DST.items()),
                       ", ".join("%d %s" % (i, n) for i, n in enumerate(alu.OPS)),
                       ", ".join("%d %s" % (v, k) for k, v in isa.ASEL.items()), bits)
    with open(path, "w") as f:
        f.write(HEADER + "\n".join(rows) + "\n" + footer)
    print("wrote", path, "(%d instructions)" % len(rows))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/02-isa.md")
