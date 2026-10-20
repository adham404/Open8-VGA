# Open8-VGA — Phase 1: Architecture, Budgets, Risks, Verification Plan

Author: Adham Elshafei <adham_mohsen@outlook.com>
Status: **Phase 1 draft — design intent, not yet verified in hardware or gate-level simulation.**
Lineage: inspired by Ben Eater's 8-bit breadboard computer; Open8-VGA is a new, larger design.

---

## 0. What the goal means, precisely

Goal: power on → full-screen editor on a VGA monitor → type assembly on a PS/2 keyboard →
assemble → run → return to the editor. Target programs: a monochrome Tetris and a
monochrome, Mario-*style* side-scroller.

Two honest constraints follow from that goal:

1. **"Any assembly code" means any code for the Open8 ISA.** Existing NES (6502) Mario or
   Game Boy (SM83) Tetris binaries/sources will not run; games must be written (or ported)
   in Open8 assembly. Examples will be provided.
2. **A text-only 80×30 display cannot show a Mario-style game.** The smallest justified
   change to the brief is therefore:
   * the character generator is **RAM, not ROM** (user-redefinable 8×16 tiles, 256 of them),
   * the text memory is a **128×32 tile map** with **hardware coarse X/Y scroll**.
   This is still a "text controller" (same pipeline, same cost class: +1 SRAM, +5 logic
   chips) but it turns it into a tile engine good enough for Tetris and a scrolling
   platformer at 8-pixel scroll granularity. No sprites, no colour (see §9 limitations).

Also added beyond the brief, with justification:
* **SPI EEPROM (25LC512, 64 KiB) for SAVE/LOAD of source.** Typing a Tetris listing every
  power-up is not a usable workflow. It is a single DIP-8 chip bit-banged from an I/O port;
  no filesystem — just 4 numbered 16 KiB slots.
* **1-bit speaker output** (piezo on an output-port bit) — one transistor, optional.

## 1. System block diagram

```
                25.175 MHz osc
                     │
           ┌─────────┴──────────┐  dot clock (25.175 MHz, 74AC domain)
           │ /8 divider (74AC161)│──────────────────────────────┐
           └─────────┬──────────┘                               │
                     │ CHAR CLK 3.147 MHz (phase φ1 / φ2)       │
          ┌──────────┴───────────┐                              │
          │ Clock/step/halt gate │ CPU CLK (gated, same edges)  │
          └──────────┬───────────┘                              │
                     ▼                                          ▼
 ┌─────────────────────────────────────┐        ┌─────────────────────────────┐
 │ CPU: microcoded, 8-bit data bus      │        │ VGA tile controller         │
 │  A B L T IR FLAGS SP  X(16) PC(16)   │        │ H/V counters + timing ROM   │
 │  MAR(16)  ROM-ALU  microcode ROM ×3  │        │ scroll adders               │
 └───────────┬─────────────┬───────────┘        │ φ1: video reads VRAM/FONT   │
   16-bit addr bus     8-bit data bus            │ φ2: CPU reads/writes        │
             │             │                     └──────┬──────────────┬──────┘
   ┌─────────┴─────────────┴────────────────────────────┴───┐          │
   │ Address decoder (74HC138s) + write-protect logic        │     74AC299 shift
   └──┬──────────┬───────────┬──────────┬──────────┬────────┘     → R/G/B, HS, VS
      ▼          ▼           ▼          ▼          ▼                    → DE-15
   FLASH 128K  SRAM 32K    I/O page   VRAM 4K    FONT RAM 4K
   (code+banks)(user+sys)  │
                           ├─ PS/2 receiver (shift reg + clock inhibit) ← mini-DIN-6
                           ├─ status / vblank / trap latches
                           ├─ ROM bank, scroll X/Y registers
                           └─ SPI/GPIO port → 25LC512 EEPROM, speaker, expansion
```

### Bus ownership
* The **CPU is the only master** of the main address/data bus. No DMA, no second master.
* VRAM and font RAM sit on **private video buses**. A 74HC157 address mux and a 74HC245
  data buffer connect each one to the CPU bus **only during φ2** (second half of the CPU
  cycle), and only when the CPU addresses that region.

### Clock domains
| Domain | Frequency | Parts |
|---|---|---|
| Dot | 25.175 MHz | oscillator, 74AC161 divider, 74AC299 shifter, pixel output buffer |
| Char / CPU | 3.147 MHz (= dot/8), CPU clock gated from it | everything else |
| PS/2 | 10–16.7 kHz, asynchronous | keyboard shift register, synchronised to CPU by status flag + inhibit |

The CPU clock is **derived from the dot clock**, so the CPU and video are phase-locked.
That is what makes the φ1/φ2 time-division arbitration deterministic: there are no
asynchronous crossings between CPU and video, and no wait states.

### Arbitration (VRAM and font RAM)
Each 318 ns character period is split:
* **φ1 (0–159 ns, CHAR CLK high):** video owns both RAMs. VRAM is read for character
  column *n*; font RAM is read for the character latched in period *n−1*.
* **φ2 (159–318 ns):** CPU owns whichever RAM it addresses (read or write).
  Write strobes are gated with φ2, so a CPU write can never land during a video read.
CPU access can therefore never corrupt the display ("snow"), and the display can never
stall the CPU. Cost: CPU reads from VRAM/font RAM must complete in half a cycle
(158.9 ns); with 74HC parts the worst case is only ~4 ns of margin at 85 °C, so that path
uses 74AC157/74AC245 (see risk R2 and docs/03-video-keyboard.md §2; fallback is a
half-speed CPU jumper).

### Reset behaviour
* Supervisor IC (MCP100-450, TO-92) holds `/RESET` low ≥ 350 ms after power-up and during
  brown-out; the manual RESET button pulls the same line.
* Reset clears: PC (74HC163 sync clear — clock is forced to run during reset), microstep
  counter, HALT, TRAP, VIOLATION latches, keyboard receiver, scroll and bank registers.
* SRAM is **not** cleared. Firmware at $0000 checks a magic signature in system RAM:
  valid → **warm boot** (back to the editor, source preserved); invalid → cold boot.
  This makes RESET the universal "STOP" key.

### Interrupts vs polling
No interrupts in v1. Keyboard and vblank are polled. The keyboard cannot lose bytes:
after one frame is received the receiver **holds PS/2 CLK low** (inhibit) until the CPU
reads the byte; the keyboard buffers internally (PS/2 protocol feature).

## 2. CPU

### Registers
| Reg | Width | Visible | Implementation |
|---|---|---|---|
| A, B | 8 | yes | 74HC574 each (clock gated by load strobe, OE to data bus) |
| X (XH:XL) | 16 | yes | 4× 74HC161 (hardware increment), 2× 74HC541 → address bus, 2× 74HC541 → data bus |
| SP | 8 (page $AF) | yes | 74HC377 + 74HC541 → data bus, 74HC541 → addr low, 74HC541 tied to $AF → addr high |
| PC | 16 | yes (jumps) | 4× 74HC163 (sync clear, sync load **from the address bus**), 2× 74HC541 → addr, 2× 74HC541 → data (for CALL) |
| FLAGS | 4 (V N Z C) | via CLC/SEC | 74HC157 source mux (ALU flags / data bus) + 74HC377 + 74HC541 → data bus |
| L, T | 8 each | no | 74HC377 each — the two ALU operand latches |
| IR | 8 | no | 74HC377 → microcode ROM address |
| MAR | 16 | no | 2× 74HC574 (OE → address bus) |
| µstep | 4 | no | 74HC163 |

### ALU — lookup-table ("ROM") ALU
* Address = `L[7:0] , T[7:0] , OP[2:0]` = 19 bits → **SST39SF040** (512 K × 8, 70 ns, DIP-32).
* OP bit 3 selects between two chip pairs (ops 0–7 / ops 8–15):
  `ALU_R0/R1` give the 8-bit result, `ALU_F0/F1` give flags `0000VNZC`.
* 4 chips replace ~15 adder/logic/mux chips, give every operation identical timing,
  and are generated by a script (`tools/alu.py`) that is also used by the simulator.
* 16 ops: ADD, ADD+1, SUB, SUB−1, AND, OR, XOR, NOT, SHL, SHR, SHL|1, SHR|$80, INC, DEC,
  CLRC (bit0←0), SETC (bit0←1). Carry-in is handled by the microcode choosing the op
  (e.g. ADC = ADD when C=0, ADD+1 when C=1), because microcode is already flag-addressed.

### Control unit
* Microcode address = `IR[7:0] , STEP[3:0] , V N Z C` = 16 bits.
* Word = 24 bits → 3× **SST39SF010A** (only the lower 64 K used; the upper half is a free
  second microcode bank selectable by jumper).
* Fields: `DSRC[4]` bus source (74HC154), `DDST[4]` bus destination (74HC154),
  `ALUOP[4]`, `ASEL[2]` address source (74HC139), `PC_INC`, `PC_LOAD`, `X_INC`,
  `FLAGS_ALU`, `END`, `HALT`, `PC_CLR`, `TRAP`, 2 spare.
* Exactly one bus driver and one bus destination per microstep **by construction**
  (decoders), plus a script validator for the remaining illegal combinations.
* Register load strobes: `REGCLK = CLK OR /LOAD` — the decoder output is only gated
  through during the low half of the clock, after microcode has settled, so decoder
  glitches can't clock registers.
* Fetch is one cycle (step 0: `MEM[PC] → IR, PC++`); most instructions take 2–5 cycles.
  At 3.147 MHz that is ≈ 0.7–1.0 MIPS.

Full ISA: [`02-isa.md`](02-isa.md) (generated from `tools/isa.py`).

## 3. Memory map (64 KiB)

| Range | Size | Device | Notes |
|---|---|---|---|
| `$0000–$3FFF` | 16 K | Flash (SST39SF010A) pages 0–3 | fixed: reset code, runtime, editor, assembler |
| `$4000–$4FFF` | 4 K | Flash page `BANK` (0–31) | banked window: font, help text, example sources |
| `$5000–$5FFF` | 4 K | I/O | 8 registers, mirrored every 8 bytes |
| `$6000–$6FFF` | 4 K | VRAM | tile map 128 × 32; address = `$6000 + row*128 + col` |
| `$7000–$7FFF` | 4 K | Font RAM | glyph `c`, line `y` at `$7000 + c*16 + y`; bit 7 = leftmost pixel |
| `$8000–$FFFF` | 32 K | SRAM (AS6C62256) | **all 32 KiB CPU-visible** |

Every address decodes to exactly one device. A15 selects SRAM; A14–A12 (74HC138) select
the other seven 4 K slices. Flash A12–A16 come from a 74HC157 mux: CPU A12/A13 + 0 for
`$0000–$3FFF`, the `BANK` register for `$4000–$4FFF`.

### I/O registers (`$5000 + n`, A2–A0 decoded, A11–A3 ignored)
| Addr | R/W | Function |
|---|---|---|
| `$5000` | R | Keyboard byte (reading it clears READY and releases PS/2 CLK) |
| `$5001` | R | KBD status: b0 READY, b1 parity bit, b2 start bit, b3 stop bit |
| `$5002` | R | SYS status: b0 VBLANK (cleared on read), b1 TRAP, b2 WRITE-VIOLATION |
| `$5002` | W | any write clears TRAP and WRITE-VIOLATION |
| `$5003` | W | ROM BANK (bits 4–0) |
| `$5004` | W | SCROLL_X (bits 6–0, tile columns) |
| `$5005` | W | SCROLL_Y (bits 4–0, tile rows) |
| `$5006` | W | OUT: b0 SPI SCK, b1 SPI MOSI, b2 /CS EEPROM, b3 speaker, b4–7 expansion |
| `$5007` | R | IN: b0 SPI MISO, b1–7 expansion |

### SRAM allocation
| Range | Size | Owner | Purpose |
|---|---|---|---|
| `$8000–$AEFF` | 11.75 K | user | assembled program + its data (entry point `$8000`) |
| `$AF00–$AFFF` | 256 B | shared | hardware stack page (SP is 8-bit, high byte fixed `$AF`) |
| `$B000–$EFFF` | 16 K | system, **write-protected from user code** | editor source buffer (plain text, LF-terminated lines) |
| `$F000–$FBFF` | 3 K | system, protected | assembler symbol table (≈ 256 symbols × 12 B) |
| `$FC00–$FFFF` | 1 K | system, protected | system variables, key state, line buffers, warm-boot magic |

**Write protection (hardware, 3 chips):** when the most recent instruction fetch came from
SRAM (A15=1 latched at fetch), writes to `$B000–$FFFF` are suppressed and the
WRITE-VIOLATION latch is set. Code fetched from ROM (firmware, runtime calls) may write
anywhere. So a buggy user program can never destroy the source or editor state.

Assembler intermediate representation: none stored — the assembler is two-pass over the
source text; pass 1 builds the symbol table, pass 2 emits bytes straight to `$8000+`.

## 4. VGA tile/text controller

* 640×480 @ 59.94 Hz, 25.175 MHz dot clock; H: 640/16/96/48 = 800, V: 480/10/2/33 = 525,
  both syncs negative. All horizontal numbers are multiples of 8 → counted in characters.
* H counter: 2× 74HC163 (0–99). V counter: 3× 74HC163 (0–524).
* **Timing ROM:** SST39SF010A addressed by `H[6:0], V[9:0]` (17 bits = exactly 128 K)
  outputs `HSYNC, VSYNC, BLANK, HRESET, VRESET, VBL_START`, registered by a 74HC574.
  Replaces ~10 comparator chips; regenerated by script; pipeline delay is compensated in
  the table.
* Tile fetch: `VRAM addr = ((V[8:4] + SCROLL_Y) mod 32) × 128 + ((H + SCROLL_X) mod 128)`
  via 3× 74HC283; `FONT addr = char × 16 + V[3:0]`.
* Serialiser: 74AC299 (load every 8 dots); pixel → 3 buffer gates → 470 Ω series into the
  75 Ω monitor termination = 0.69 V full-scale (VGA spec 0.7 V). Jumpers choose
  white / green / amber.
* Cursor: drawn by firmware (inverse glyph); default font has inverse copies in 128–255.
* VRAM / font: AS6C6264-55 (8 K × 8, 55 ns), upper 4 K unused.

## 5. PS/2 keyboard

* Mini-DIN-6: pin 1 DATA, 3 GND, 4 +5 V (polyfuse), 5 CLK. 4.7 kΩ pull-ups on CLK/DATA.
* 74HC14 Schmitt on CLK; 2× 74HC164 shift 11 bits on the falling CLK edge; 74HC161 bit
  counter; at 11 bits, READY (74HC74) sets and a 74HC05 open-drain pulls CLK low (inhibit).
* Reading `$5000` clears READY and the counter. RC + Schmitt timeout (~2 ms idle) resets
  a half-received frame.
* Firmware decodes Scan Code Set 2 (make, `F0` break, `E0` extended), tracks a 128-bit
  key-down table (for games) and an 16-byte ASCII/command queue (for the editor).
* A USB keyboard needs a keyboard that supports PS/2 mode plus a passive adapter; most
  modern USB-only keyboards do not. Documented in the BOM notes.

## 6. Clock, reset, debug

* Modes (rotary/slide + buttons), all through **one clock-enable mux** feeding a
  glitch-free gate (enable latched on the falling edge), so manual and automatic sources
  can never fight: RUN (3.147 MHz), SLOW (555, ~1–200 Hz, one cycle per period, edge-
  synchronised), STEP (one microcycle per press), INSTR-STEP (run until µstep = 0),
  HALT (from `HLT`, cleared by CONTINUE or RESET). Half-speed jumper for the whole CPU.
* LED indicators (optional, DNP-able): data bus, address bus, IR, µstep, flags, HALT,
  clock. Driven via 74HC541 buffers, never directly from the bus.
* Headers: 2×20 logic-analyser (A0–15, D0–7, CLK, /RESET, µstep, /MEMR, /MEMW, /ROMCS,
  /RAMCS, /IOCS, /VRAMCS, HS, VS, PS2 CLK/DATA), ROM-programming notes, expansion
  (data bus, A0–A7, I/O selects, GPIO), test points for every clock and supply.

## 7. Power

* USB-C receptacle, power only (5.1 kΩ CC pull-downs → 5 V from any USB-C source),
  plus a 2-pin screw terminal alternative. 2 A polyfuse, SMBJ5.0A TVS, P-MOSFET
  reverse-polarity protection on the screw-terminal path, power LED.
* Estimated draw: ≈ 100 ICs; 9 flash (≈ 15–25 mA each active), 3 SRAM (≈ 15–30 mA),
  ≈ 85 HC logic (≈ 1–5 mA each at 3 MHz), LEDs (40 × 3 mA). **Budget ≈ 0.6–0.9 A**;
  requires a ≥ 1.5 A USB-C supply. To be measured at bring-up.
* 100 nF X7R per IC at the VCC pin, 10 µF per board region, 470 µF bulk at the input.
* 4-layer PCB (signal / GND / 5 V / signal): justified by ≈ 100 DIP packages, two
  16-bit buses and a 25 MHz clock domain. Estimated 300 × 230 mm.

## 8. Budgets

### ROM (SST39SF010A, 128 KiB = 32 pages of 4 KiB)
| Content | Est. size | Location |
|---|---|---|
| Reset, warm/cold boot, trap handler | 0.5 K | fixed |
| Runtime (PUTC, PRINT, CLS, GOTOXY, scroll, GETKEY, key state, delay, beep, hex/dec print) | 2.5 K | fixed |
| PS/2 decoder + SPI EEPROM save/load | 1.5 K | fixed |
| Editor | 3 K | fixed |
| Assembler (2-pass, labels, expressions subset) | 6 K | fixed |
| Help viewer + messages | 1 K | fixed |
| **Fixed total** | **14.5 K of 16 K** (estimate) — **actual after Phase 4: 8.8 K** | margin 7 K |
| Font 8×16 × 256 | 4 K | bank page 4 |
| Help text (ISA, syntax, map, keys, debugging) | ≤ 12 K | pages 5–7 |
| Example sources (hello, math, loop, branch, keyboard echo, Tetris, scroller) | ≤ 40 K | pages 8–17 |
| Spare | 56 K | pages 18–31 |

### RAM — see §3. User program max 11.75 K, source max 16 K characters.
Tetris (estimated 1.5–3 K code, 8–12 K source) fits. A Mario-style scroller is feasible as
a compact demo (≈ 4–6 K code+level data, ≤ 16 K source); a full-scale SMB clone is not.

### Speed
≈ 0.8 MIPS → ≈ 13 000 instructions per 60 Hz frame. Tetris needs < 2 000 per frame.
Scrolling costs one SCROLL_X write plus one 30-byte column per 8 pixels.

## 9. Known limitations (by design)
* Monochrome; no hardware sprites; scroll granularity 8 pixels (no fine scroll).
* No interrupts; programs must poll keyboard/vblank (runtime routines do this).
* A program that never returns can only be stopped by RESET (source is preserved).
* 64 KiB address space, no MMU; protection covers only the system region.

## 10. Component shortlist (to be datasheet- and stock-verified in Phase 6)
| Function | Candidate | Package | Status |
|---|---|---|---|
| Firmware / microcode / timing flash | SST39SF010A-70-4C-PHE (Microchip) | DIP-32 | candidate |
| ALU flash | SST39SF040-70-4C-PHE (Microchip) | DIP-32 | candidate |
| Main SRAM | AS6C62256-55PCN (Alliance) | DIP-28 | candidate |
| Video/Font SRAM | AS6C6264-55PCN (Alliance) | DIP-28 | candidate |
| Dot-clock divider | 74AC161 / 74ACT161 (DIP) | DIP-16 | **verify DIP availability** |
| Pixel shifter | 74AC299 (DIP) | DIP-20 | **verify DIP availability**; alt: 74F166 |
| Oscillator | 25.175 MHz 5 V full-can (DIP-14 footprint) | DIP-14/8 | **verify** |
| Logic | 74HC00/02/04/05/08/14/32/74/138/139/154/157/161/163/164/245/283/377/541/574 | DIP | standard |
| Reset supervisor | MCP100-450DI/TO | TO-92 | candidate |
| Save EEPROM | 25LC512-I/P | DIP-8 | candidate |
| Connectors | DE-15 HD female (VGA), mini-DIN-6 female (PS/2), USB-C 6-pin power | THT | candidate |
| Programmer (external, one-off) | XGecu T48 / TL866II+ | — | needed for all flash chips |

## 11. Risk analysis (highest first)
| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | 25 MHz dot-clock parts not available in DIP (74AC/74F) | no video | verify early; fallback: SMD (SOIC) for the 3 dot-domain parts only |
| R2 | CPU reads of VRAM/font RAM in φ2: 135–155 ns worst case vs 158.9 ns with 74HC | flaky reads when hot | 74AC157/74AC245 in that path (> 70 ns margin); half-speed CPU jumper |
| R3 | Main-bus critical path (µcode ROM 70 + decode + ROM-ALU 70 + setup) vs 318 ns | CPU must run slower | static timing budget in Phase 2b; half-speed jumper |
| R4 | Gated register clocks (`CLK OR /LOAD`) — skew between registers | rare mis-latch | all strobes from the same 74HC32 family, locally decoupled; validate on scope |
| R5 | Fixed ROM 16 K too small for editor + assembler | missing features | **resolved in Phase 4**: 8.8 K used; bank pages hold tables, help and examples |
| R6 | 16 K source limit for larger games | game size | SAVE/LOAD slots; compact syntax; documented |
| R7 | ~100-chip board cost/size, 4-layer | cost | accept; optional LED/debug parts DNP |
| R8 | PS/2 keyboards scarce | input | document compatible keyboards / adapters |

## 12. Verification plan
| Stage | What | How | Status |
|---|---|---|---|
| V1 | ISA ↔ microcode consistency | `tools/microcode.py --check`: contention rules, step-0 identity, END reachability on every flag path | Phase 2 |
| V2 | Microcode correctness | **differential test**: microcode-level simulator (executes the generated ROM bytes) vs independent ISA reference model, every opcode, random operands, all flag states | Phase 2 |
| V3 | ALU ROM | exhaustive 16 × 256 × 256 comparison against reference semantics | Phase 2 |
| V4 | Assembler | unit tests per instruction form, errors, golden binaries | Phase 2 |
| V5 | Memory decode & protection | simulator tests at every region boundary | Phase 2/3 |
| V6 | VGA timing ROM | generated table checked against VESA numbers; simulated frame rendered to PNG | Phase 3 |
| V7 | PS/2 | simulator model fed scan-code streams (make/break/E0/overflow) | Phase 3 |
| V8 | Firmware | scripted keyboard input into simulator: type → assemble → run → compare VRAM to expected screen | Phase 4–5 |
| V9 | Gate-level | Verilog netlist from KiCad + 74xx behavioural models (needs Icarus Verilog — **not installed yet**) | Phase 5/6 |
| V10 | PCB | ERC/DRC, footprint/pinout review, timing-critical nets | Phase 6 |
| V11 | Hardware | incremental bring-up plan | Phase 8 — **requires a physical board** |

Nothing in this project is claimed to be tested on hardware until a board exists.
