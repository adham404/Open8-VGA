# Open8 Instruction Set (generated — do not edit; run `python3 tools/gendoc.py`)

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
| `$00` | `HLT` | 1 | 2 | - | Stop the CPU clock. CONTINUE resumes at the next instruction; RESET returns to the editor. |
| `$01` | `NOP` | 1 | 2 | - | Do nothing. |
| `$02` | `LD A, #n` | 2 | 2 | - | A <- n |
| `$03` | `LD A, [addr]` | 3 | 4 | - | A <- mem[addr] |
| `$04` | `LD A, [X]` | 1 | 2 | - | A <- mem[X] |
| `$05` | `LD A, [X+]` | 1 | 2 | - | A <- mem[X]; X <- X+1 |
| `$06` | `ST A, [addr]` | 3 | 4 | - | mem[addr] <- A |
| `$07` | `ST A, [X]` | 1 | 2 | - | mem[X] <- A |
| `$08` | `ST A, [X+]` | 1 | 2 | - | mem[X] <- A; X <- X+1 |
| `$09` | `LD B, #n` | 2 | 2 | - | B <- n |
| `$0A` | `LD B, [addr]` | 3 | 4 | - | B <- mem[addr] |
| `$0B` | `LD B, [X]` | 1 | 2 | - | B <- mem[X] |
| `$0C` | `LD B, [X+]` | 1 | 2 | - | B <- mem[X]; X <- X+1 |
| `$0D` | `ST B, [addr]` | 3 | 4 | - | mem[addr] <- B |
| `$0E` | `ST B, [X]` | 1 | 2 | - | mem[X] <- B |
| `$0F` | `ST B, [X+]` | 1 | 2 | - | mem[X] <- B; X <- X+1 |
| `$10` | `LD X, #nn` | 3 | 3 | - | X <- nn |
| `$11` | `LD SP, #n` | 2 | 2 | - | SP <- n (stack is at $AF00+SP, grows down, SP points at the last pushed byte) |
| `$12` | `MOV A, B` | 1 | 2 | - | A <- B |
| `$13` | `MOV B, A` | 1 | 2 | - | B <- A |
| `$14` | `MOV A, XL` | 1 | 2 | - | A <- XL |
| `$15` | `MOV A, XH` | 1 | 2 | - | A <- XH |
| `$16` | `MOV B, XL` | 1 | 2 | - | B <- XL |
| `$17` | `MOV B, XH` | 1 | 2 | - | B <- XH |
| `$18` | `MOV XL, A` | 1 | 2 | - | XL <- A |
| `$19` | `MOV XH, A` | 1 | 2 | - | XH <- A |
| `$1A` | `MOV XL, B` | 1 | 2 | - | XL <- B |
| `$1B` | `MOV XH, B` | 1 | 2 | - | XH <- B |
| `$1C` | `MOV A, SP` | 1 | 2 | - | A <- SP |
| `$1D` | `MOV SP, A` | 1 | 2 | - | SP <- A |
| `$1E` | `ADD A, B` | 1 | 4 | Z N C V | A <- A + B |
| `$1F` | `ADD A, #n` | 2 | 4 | Z N C V | A <- A + n |
| `$20` | `ADD A, [addr]` | 3 | 6 | Z N C V | A <- A + mem[addr] |
| `$21` | `ADD A, [X]` | 1 | 4 | Z N C V | A <- A + mem[X] |
| `$22` | `ADC A, B` | 1 | 4 | Z N C V | A <- A + B + C |
| `$23` | `ADC A, #n` | 2 | 4 | Z N C V | A <- A + n + C |
| `$24` | `ADC A, [addr]` | 3 | 6 | Z N C V | A <- A + mem[addr] + C |
| `$25` | `ADC A, [X]` | 1 | 4 | Z N C V | A <- A + mem[X] + C |
| `$26` | `SUB A, B` | 1 | 4 | Z N C V | A <- A - B (C = borrow) |
| `$27` | `SUB A, #n` | 2 | 4 | Z N C V | A <- A - n (C = borrow) |
| `$28` | `SUB A, [addr]` | 3 | 6 | Z N C V | A <- A - mem[addr] (C = borrow) |
| `$29` | `SUB A, [X]` | 1 | 4 | Z N C V | A <- A - mem[X] (C = borrow) |
| `$2A` | `SBC A, B` | 1 | 4 | Z N C V | A <- A - B - C |
| `$2B` | `SBC A, #n` | 2 | 4 | Z N C V | A <- A - n - C |
| `$2C` | `SBC A, [addr]` | 3 | 6 | Z N C V | A <- A - mem[addr] - C |
| `$2D` | `SBC A, [X]` | 1 | 4 | Z N C V | A <- A - mem[X] - C |
| `$2E` | `AND A, B` | 1 | 4 | Z N C V | A <- A AND B (C=0, V=0) |
| `$2F` | `AND A, #n` | 2 | 4 | Z N C V | A <- A AND n (C=0, V=0) |
| `$30` | `AND A, [addr]` | 3 | 6 | Z N C V | A <- A AND mem[addr] (C=0, V=0) |
| `$31` | `AND A, [X]` | 1 | 4 | Z N C V | A <- A AND mem[X] (C=0, V=0) |
| `$32` | `OR A, B` | 1 | 4 | Z N C V | A <- A OR B (C=0, V=0) |
| `$33` | `OR A, #n` | 2 | 4 | Z N C V | A <- A OR n (C=0, V=0) |
| `$34` | `OR A, [addr]` | 3 | 6 | Z N C V | A <- A OR mem[addr] (C=0, V=0) |
| `$35` | `OR A, [X]` | 1 | 4 | Z N C V | A <- A OR mem[X] (C=0, V=0) |
| `$36` | `XOR A, B` | 1 | 4 | Z N C V | A <- A XOR B (C=0, V=0) |
| `$37` | `XOR A, #n` | 2 | 4 | Z N C V | A <- A XOR n (C=0, V=0) |
| `$38` | `XOR A, [addr]` | 3 | 6 | Z N C V | A <- A XOR mem[addr] (C=0, V=0) |
| `$39` | `XOR A, [X]` | 1 | 4 | Z N C V | A <- A XOR mem[X] (C=0, V=0) |
| `$3A` | `CMP A, B` | 1 | 4 | Z N C V | flags of A - B; A unchanged (JC = A < B unsigned) |
| `$3B` | `CMP A, #n` | 2 | 4 | Z N C V | flags of A - n; A unchanged (JC = A < n unsigned) |
| `$3C` | `CMP A, [addr]` | 3 | 6 | Z N C V | flags of A - mem[addr]; A unchanged (JC = A < mem[addr] unsigned) |
| `$3D` | `CMP A, [X]` | 1 | 4 | Z N C V | flags of A - mem[X]; A unchanged (JC = A < mem[X] unsigned) |
| `$3E` | `NOT A` | 1 | 3 | Z N C V | A <- NOT A (C=0, V=0) |
| `$3F` | `SHL A` | 1 | 3 | Z N C V | C <- A7, A <- A << 1 |
| `$40` | `SHR A` | 1 | 3 | Z N C V | C <- A0, A <- A >> 1 (logical) |
| `$41` | `ROL A` | 1 | 3 | Z N C V | A <- A << 1 \| C, C <- old A7 |
| `$42` | `ROR A` | 1 | 3 | Z N C V | A <- C << 7 \| A >> 1, C <- old A0 |
| `$43` | `INC A` | 1 | 3 | Z N C V | A <- A + 1 (C = carry out) |
| `$44` | `DEC A` | 1 | 3 | Z N C V | A <- A - 1 (C = borrow) |
| `$45` | `NOT B` | 1 | 3 | Z N C V | B <- NOT B (C=0, V=0) |
| `$46` | `SHL B` | 1 | 3 | Z N C V | C <- B7, B <- B << 1 |
| `$47` | `SHR B` | 1 | 3 | Z N C V | C <- B0, B <- B >> 1 (logical) |
| `$48` | `ROL B` | 1 | 3 | Z N C V | B <- B << 1 \| C, C <- old B7 |
| `$49` | `ROR B` | 1 | 3 | Z N C V | B <- C << 7 \| B >> 1, C <- old B0 |
| `$4A` | `INC B` | 1 | 3 | Z N C V | B <- B + 1 (C = carry out) |
| `$4B` | `DEC B` | 1 | 3 | Z N C V | B <- B - 1 (C = borrow) |
| `$4C` | `INC X` | 1 | 2 | - | X <- X + 1 (flags unchanged) |
| `$4D` | `DEC X` | 1 | 4–5 | C (Z N V undefined) | X <- X - 1; C = 16-bit borrow |
| `$4E` | `ADD X, A` | 1 | 5–6 | C (Z N V undefined) | X <- X + A (A unsigned); C = 16-bit carry |
| `$4F` | `CLC` | 1 | 3 | C | C <- 0 |
| `$50` | `SEC` | 1 | 3 | C | C <- 1 |
| `$51` | `JMP addr` | 3 | 4 | - | PC <- addr |
| `$52` | `JMP X` | 1 | 2 | - | PC <- X |
| `$53` | `JZ addr` | 3 | 4 | - | if Z=1: PC <- addr |
| `$54` | `JNZ addr` | 3 | 4 | - | if Z=0: PC <- addr |
| `$55` | `JC addr` | 3 | 4 | - | if C=1: PC <- addr |
| `$56` | `JNC addr` | 3 | 4 | - | if C=0: PC <- addr |
| `$57` | `JN addr` | 3 | 4 | - | if N=1: PC <- addr |
| `$58` | `JNN addr` | 3 | 4 | - | if N=0: PC <- addr |
| `$59` | `JV addr` | 3 | 4 | - | if V=1: PC <- addr |
| `$5A` | `JNV addr` | 3 | 4 | - | if V=0: PC <- addr |
| `$5B` | `CALL addr` | 3 | 10 | - | push return address (high, then low); PC <- addr |
| `$5C` | `CALL X` | 1 | 8 | - | push return address; PC <- X |
| `$5D` | `RET` | 1 | 8 | - | pop return address; PC <- it |
| `$5E` | `PUSH A` | 1 | 4 | - | SP <- SP-1; mem[$AF00+SP] <- A |
| `$5F` | `POP A` | 1 | 4 | - | A <- mem[$AF00+SP]; SP <- SP+1 |
| `$60` | `PUSH B` | 1 | 4 | - | SP <- SP-1; mem[$AF00+SP] <- B |
| `$61` | `POP B` | 1 | 4 | - | B <- mem[$AF00+SP]; SP <- SP+1 |
| `$62` | `PUSH X` | 1 | 7 | - | push XH, then XL |
| `$63` | `POP X` | 1 | 7 | - | pop XL, then XH |
| `$64` | `PUSHF` | 1 | 4 | - | push FLAGS (0000VNZC) |
| `$65` | `POPF` | 1 | 4 | all | pop FLAGS |

## Microinstruction format (24 bits, 3 × SST39SF010A)
| Bits | Field | Values |
|---|---|---|
| 3–0 | DSRC (bus source) | 0 NONE, 1 A, 2 B, 3 ALU, 4 MEM, 5 XL, 6 XH, 7 SP, 8 PCL, 9 PCH, 10 FLAGS |
| 7–4 | DDST (bus destination) | 0 NONE, 1 A, 2 B, 3 T, 4 L, 5 IR, 6 MARL, 7 MARH, 8 XL, 9 XH, 10 SP, 11 MEM, 12 FLAGS |
| 11–8 | ALUOP | 0 ADD, 1 ADD1, 2 SUB, 3 SUB1, 4 AND, 5 OR, 6 XOR, 7 NOT, 8 SHL, 9 SHR, 10 SHL1, 11 SHR1, 12 INC, 13 DEC, 14 CLRC, 15 SETC |
| 13–12 | ASEL (address source) | 0 PC, 1 MAR, 2 X, 3 SP |
| 14 | PC_INC | 1 = active |
| 15 | PC_LOAD | 1 = active |
| 16 | X_INC | 1 = active |
| 17 | FLAGS_ALU | 1 = active |
| 18 | END | 1 = active |
| 19 | HALT | 1 = active |
| 20 | PC_CLR | 1 = active |
| 21 | TRAP | 1 = active |
Microcode address = `IR[7:0] STEP[3:0] V N Z C`. Step 0 of every opcode is the fetch
`MEM[PC] -> IR, PC+1`. `END` resets the step counter so the next cycle is a fetch.
Validation rules (enforced by `tools/microcode.py`): one source and one destination per
step by construction; a destination needs a source; no memory-to-memory; at most one of
PC_INC/PC_LOAD/PC_CLR; no PC_LOAD from PC; no FLAGS from ALU and bus together; no X_INC
while loading X; IR loads only in step 0; every sequence ends with END within 16 steps.
