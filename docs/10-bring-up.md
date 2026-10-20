# 10 — Bring-up plan (Rev A)

Author: Adham Elshafei

Status: **plan only; the board has not been powered yet.** Every predicted value below comes from
the gate-level simulator (`hardware/gatesim.py`, driven by `tests/test_hardware.py`) or the
microcode-level CPU model (`tools/sim.py`, `tools/fwsim.py`) running the real ROM images. A
measurement that disagrees with the prediction points at the stage you just added.

Assembly comes first: [09-assembly.md](09-assembly.md). All ICs are socketed, so each stage
adds a defined set of chips. **Power off before inserting or removing any chip.**

## 0. Equipment and conventions
* Bench supply, 5.00 V with an adjustable current limit, connected to **J5 pins 33/34 (VCC)
  and 35–37 (GND)**. This bypasses F2. Switch to USB-C (J3) once stage 5 works.
* Multimeter; oscilloscope with at least 100 MHz bandwidth and a short ground spring (the dot
  clock is 25 MHz); logic analyser on **J4** (pinout in doc 09 §6: A0–15, D0–7, CPUCLK, RST_N,
  STEP0–3, WR_N, RD_N, ROMSEL_N, HSYNC, VSYNC, KCLK, KDATA, CHARCLK).
* VGA monitor, PS/2 keyboard, flash programmer.
* Times are measured from the rising edge of CHARCLK (J4 pin 38). 1 dot = 39.72 ns,
  1 character/CPU cycle = 8 dots = 317.8 ns, 1 line = 800 dots = 31.78 µs.
* Write down the supply current at every stage. If inserting one group of chips makes the current
  jump by more than about 100 mA, a chip is in backwards or two outputs are fighting.
  [01-architecture.md](01-architecture.md) §7 estimates 0.6–0.9 A, including 40 LEDs that
  Rev A does not have. Expect roughly 0.5–0.8 A for the full board. This is an estimate,
  not a simulated figure.

The simulator checks that the stages need:

```bash
python3 -m unittest tests.test_hardware -v
```

Stage chip lists below were derived from the netlist: for each stage, the gates that drive the
nets under test were traced back through `design.py`. Gate packages are shared between sheets
(U96, a "keyboard" 74HC04, also makes HRES_N and VRES_N for the video counters), so the lists
follow the wiring, not the sheet names.

## Stage 1 — Power only (no ICs)
Sockets empty; X1 may be soldered in.

| Check | How | Expect |
|---|---|---|
| VCC–GND short | ohmmeter J5.33 → J5.35, supply off | climbs as C6 (470 µF) charges, settling far above 1 kΩ. Under 10 Ω = solder bridge |
| VBUS–VCC path | J3 VBUS (F2 pin 1) → J5.33 | under 1 Ω (polyfuse F2) |
| Supply current | bench 5.00 V, limit 100 mA | a few mA (PWR LED D3 about 3 mA through R21, MCP130 µA), plus X1's own supply current if it is fitted |
| VCC at every socket | DMM on each socket's VCC and GND pins | 5.0 V everywhere: pin 14/7 (DIP-14), 16/8 (DIP-16), 20/10 (DIP-20), 24/12 (U23, U24), 28/14 (U201–U203), 32/16 (flash), 8/1 (U10), 8/4 (U90) |
| Reset supervisor | U7 pin 1 (RSTRAW_N), scope at power-on | low for about 350 ms (MCP130), then high through R1. Low while SW1 RESET is held |
| Buttons | U9 pin 1 (STEP), U9 pin 3 (CONTINUE) | 5 V idle, 0 V pressed, edges slowed by 47 k × 100 nF (about 5 ms) |
| Switches | SW2 pin 2 (STEP_MODE), SW3 pin 2 (SLOW_SEL) | 5 V in one position, 0 V in the other. Note which slider position is STEP and which is SLOW (doc 09 §5) |
| Jumpers | JP1–JP5 pin 1 | 0 V open (10 k pull-downs R5, R6, R11, R13, R15), 5 V fitted |
| USB-C | remove the bench supply, plug in a USB-C charger | VCC = 5 V minus the F2 drop. The CC pull-downs R19/R20 are what make a USB-C source turn on |

Then fit U10 (NE555): SLOWCLK at U10 pin 3 is a square wave, about 0.7 Hz with RV1 at full
resistance, getting faster as RV1 is turned down.

## Stage 2 — Clock and dot counter
Insert **X1 (if socketed), U1 (74AC161), U2 (74AC04), U3 (74HC86), U4 (74HC08), U5 (74AC574)**.
U4's other three gates (PULSE, RUNOK, CE_RUN) have floating inputs until stage 4. They drive
nothing yet, so this is fine for a short test.

Scope, timing relative to CHARCLK rising (simulated sequence, one character):

| Net | Probe | Expect |
|---|---|---|
| DOTCLK | X1 pin 8 / U1 pin 2 | 25.175 MHz, 39.72 ns |
| DOT0, DOT1, DOT2 | U1 pins 14, 13, 12 | 12.59, 6.29, 3.147 MHz, each a clean ÷2 of the one before |
| CHARCLK | U2 pin 2, J4 pin 38 | 3.147 MHz, 50 % (high for dots 0–3: 158.9 ns), = NOT DOT2 |
| DOTCLK_N | U2 pin 4 | inverted dot clock |
| PH2 | U5 pin 18 | rises at dot 4.5 (178.8 ns), falls at dot 0.5 of the next character (+19.9 ns); 50 % |
| WIN | U5 pin 19 | high from dot 5.5 to dot 7.5: rises at 218.5 ns, 79.4 ns wide, ends 19.9 ns before the next CHARCLK edge |

The simulator's phase table (`gatesim.Board.half_dot`, half-dot steps from reset) gives exactly
this sequence: CHARCLK falls with DOT2, PH2 changes half a dot after each CHARCLK edge, WIN is
the two-dot window before the edge. Expect a few ns of extra AC gate delay on real parts. WIN
and PH2 must be glitch-free: they come straight from a register. If they glitch, suspect a
missing decoupling capacitor near U5.

## Stage 3 — Video sync
Insert **U96 (74HC04), U103–U107 (74HC163), U108 (vga_timing.bin), U109 (74AC574), U129 (74AC574)**.
Floating until later stages: U96's KREADY, VRSEL_N, FNSEL_N and VBEN inputs, and U129's D1
(PIXR). None of them drives anything installed yet.

Connect a monitor. It should lock to **640×480 at 60 Hz** and show black: there is no pixel
path yet, and no colour without JP3–JP5.

| Net | Probe | Expect (sim: `test_pixels_and_syncs_match_reference`) |
|---|---|---|
| HSYNC | J2 pin 13, J4 pin 34 (U129 pin 17) | **31.469 kHz**, period 800 dots (31.78 µs), negative, low for **96 dots (3.81 µs)** |
| VSYNC | J2 pin 14, J4 pin 35 (U129 pin 16) | **59.94 Hz** (525 lines, 16.68 ms), negative, low for **2 lines (63.6 µs)**, on lines 490–491 |
| BLANKQ | U129 pin 18 | high for 160 dots per line (front porch 16, sync 96, back porch 48) and for lines 480–524 |
| HRESET | U109 pin 16 | one character (317.8 ns) high pulse per line: the H counter runs 0–99 |
| VRESET | U109 pin 15 | one pulse per frame: the V counter runs 0–524 |
| H counter | U103 pins 14, 13, 12, 11 | CHARCLK ÷2, ÷4, ÷8, ÷16 (reset every 100 characters) |

The timing ROM makes HRESET and VRESET for every counter state past the end (H ≥ 100,
V ≥ 525), so a counter that powers up out of range is back in step within one line or frame.
A rolling or unlocked picture means a wrong timing image (check U108's checksum, doc 09 §4),
a wrong counter, or HRES_N/VRES_N not reaching the counters' CLR pins (U96).

## Stage 4 — CPU single-step
Insert the rest of the CPU and the keyboard receiver: **U6, U8, U9, U11–U16, U20–U37, U42–U89,
U91–U95, U97–U102, U117**, the programmed flash **U17–U19, U38–U41, U200**, and SRAM **U201**
(U10 and U5 are already in). Leave U90 (EEPROM) and the rest of the video out. The only input
left floating is U129's PIXR.
Set **SW2 = STEP, SW3 = STEP (not SLOW)**, JP1 and JP2 open.

1. Power on. HALT LED D4 off. RST_N (J4 pin 26) goes high about 350 ms after power-up.
   CPUCLK (J4 pin 25) stays low: in step mode the clock runs only for a press or during reset.
2. **Press and release SW1 RESET.** During reset the clock is forced to run (CE_RAW includes
   RST), so the PC and microstep counter clear and step 0 fetches the opcode at $0000 into
   IR. The state is then fixed and matches the "after reset" row below.
3. Press **SW4 STEP** once per row. Each press is exactly one microcycle (sim:
   `test_step_mode_and_step_button`).

The address bus and STEP0–3 are static between presses. The data bus is driven only while
WIN is high (once every 317.8 ns, even with the CPU clock stopped). For a memory read, trigger
the analyser on RD_N falling. A multimeter or logic probe still reads it as roughly steady.

Predicted by `gatesim` with the real ROMs, after the given press (the microstep about to execute):

| Press | STEP | PC | IR | A bus | D bus | RD_N | WR_N | ROMSEL_N | Instruction |
|---|---|---|---|---|---|---|---|---|---|
| after reset | 0 | 0000 | 51 | 0000 | 51 | pulses | 1 | 0 | fetch `JMP $0030` |
| 1 | 1 | 0001 | 51 | 0001 | 30 | pulses | 1 | 0 | operand low |
| 2 | 2 | 0002 | 51 | 0002 | 00 | pulses | 1 | 0 | operand high |
| 3 | 3 | 0003 | 51 | 0030 | – | 1 | 1 | 0 | PC ← MAR |
| 4 | 0 | 0030 | 51 | 0030 | 1C | pulses | 1 | 0 | fetch `MOV A, SP` |
| 5 | 1 | 0031 | 1C | 0031 | – | 1 | 1 | 0 | A ← SP |
| 6 | 0 | 0031 | 1C | 0031 | 06 | pulses | 1 | 0 | fetch `ST A, [$FC24]` |
| 7 | 1 | 0032 | 06 | 0032 | 24 | pulses | 1 | 0 | |
| 8 | 2 | 0033 | 06 | 0033 | FC | pulses | 1 | 0 | |
| 9 | 3 | 0034 | 06 | FC24 | xx | 1 | **0** | 1 | write A to SRAM (xx = SP at power-up, random) |
| 10 | 0 | 0034 | 06 | 0034 | 11 | pulses | 1 | 0 | fetch `LD SP, #0` |
| 11 | 1 | 0035 | 11 | 0035 | 00 | pulses | 1 | 0 | |
| 12 | 0 | 0036 | 11 | 0036 | 03 | pulses | 1 | 0 | fetch `LD A, [$5002]` |
| 13 | 1 | 0037 | 03 | 0037 | 02 | pulses | 1 | 0 | |
| 14 | 2 | 0038 | 03 | 0038 | 50 | pulses | 1 | 0 | |
| 15 | 3 | 0039 | 03 | 5002 | 00* | pulses | 1 | 1 | read SYS_STATUS (*bit 0 = VBLANK latch, may be 1) |
| 16 | 0 | 0039 | 03 | 0039 | 06 | pulses | 1 | 0 | fetch `ST A, [$FC23]` |
| 19 | 3 | 003C | 06 | FC23 | A | 1 | **0** | 1 | write |
| 23 | 3 | 003F | 06 | 5002 | A | 1 | **0** | 1 | write SYS_STATUS (clears TRAP/VIOL) |
| 24 | 0 | 003F | 06 | 003F | 02 | pulses | 1 | 0 | fetch `LD A, #0` |
| 29 | 3 | 0044 | 06 | 5004 | 00 | 1 | **0** | 1 | write SCROLL_X |

"pulses" = RD_N goes low during WIN in each character (a memory read). WR_N is the
decoder output and stays low for the whole write microstep; the actual write strobe
(RAMWE_N / VRWE_N) is only the WIN window. IR is $51 after reset because the reset clocks
run a real fetch. This follows `firmware/boot.asm` line by line.

Then:
* **SW3 = SLOW:** the 555 now steps the CPU, one microcycle per SLOWCLK period. Watch
  STEP0–3 count on the analyser.
* **SW2 = RUN:** CPUCLK = CHARCLK, 3.147 MHz continuous. Without VRAM the screen stays black, but
  the CPU boots. After about 354,000 cycles (112 ms) the firmware waits for a key: the PC stays
  in **$02C2–$034A** (the `GK_L` key loop) and the only data reads outside ROM are $5001
  (KBD_STATUS) and $AFF7/8, $FC21/2 (`fwsim`, MicroCPU run of `firmware.bin`).
* **JP1 fitted:** CPUCLK pulses on every other character, and the CPU runs at half speed
  (sim: `test_half_speed_jumper`, ratio 0.5).
* If the trace goes wrong at a fetch, check the data byte against `firmware.bin`. If the
  opcode is right but the sequence of steps is wrong, look at U17–U19 (microcode order,
  JP2). If the data is right but a register gets the wrong value, look at the ALU ROMs
  U38–U41.

## Stage 5 — Video RAM and firmware boot
Insert the rest of the video section: **U110–U116, U118–U128, U130, U131, U202, U203**. With
the stage 4 chips that is all 132 logic packages, and no input floats. Fit JP3–JP5. SW2 = RUN.

| Time after power-on | Expect (sim) |
|---|---|
| 0–350 ms | reset held by the MCP130 |
| + 0–42 ms | screen shows random characters (VRAM and font RAM power up random) while the firmware copies the font from bank 4 to U203 (done at about 132,000 cycles) |
| + 66 ms | first VRAM write (about 209,000 cycles) |
| + 112 ms | welcome screen complete (353,441 cycles), firmware idle in `GK_L` |

Expected screen, as rendered from the simulated VRAM:

```
row  2  Welcome! This computer boots straight into an assembly language editor.
row  4    1. EDIT      Type your program. Arrows, Home/End, PgUp/PgDn move around.
row  5    2. ASSEMBLE  Press F2. Mistakes are reported with their line number.
row  6    3. RUN       Press F3. Your program starts at address $8000.
row  7    4. STOP      Press the RESET button. Your program text is kept.
row  8    5. RETURN    End a program with RET (or CALL EXIT) to come back here.
row 10    F1 opens the built-in help: instructions, registers, syntax, memory map.
row 11    F5 loads an example program.  F9 starts a new, empty program.
row 12    F4 saves your program to EEPROM, F6 loads it back (4 slots).
row 14  A small example is already in the editor - press F3 to run it.
row 16  Press any key to start.
```

| Measure | Probe | Expect |
|---|---|---|
| R, G, B | J2 pins 1–3, monitor connected (75 Ω) | about 0.69 V for an "on" pixel, 0 V off and during blanking |
| first pixel | HSYNC falling → first visible dot | 96 + 48 = 144 dots (5.72 µs); the sim compares 8 full lines against `video.render()` pixel for pixel |
| VRAM arbitration | U114 pin 1 (PH2) vs U202 pin 22 (/OE) | CPU access only in φ2; the sim records no bus contention (`b.contention == []`) |

The simulator's checks for this stage: `test_pixels_and_syncs_match_reference` (pixels and
syncs), `test_every_instruction_matches_microcode_cpu` (VRAM, font RAM, SCROLL_X and SRAM
contents after every instruction form), `test_firmware_boot_matches_for_20000_cycles` (the
netlist and the CPU model agree for 20,000 boot cycles), and `test_write_protection`.

Symptoms:
* Random characters that never clear: the CPU is not running. Go back to stage 4 with SW2 = RUN.
* Text appears but the glyphs are wrong: suspect the font path (U120–U122, U125–U127, U203).
* Text is in the wrong place or wraps: suspect SCROLL_X/Y (U79, U80) or the adders U110–U113.
* Speckles or wrong characters only when the CPU writes: suspect the φ2 path (U114–U116,
  U118, U117, U95). Fit JP1. If the speckles stop, it is a timing problem: check that every AC
  position really has an AC part (doc 09 §1).

## Stage 6 — Keyboard
Power off, plug in a PS/2 keyboard (PS/2 is not hot-pluggable), power on. J1 pin 4 gets 5 V
through F1 (200 mA). The keyboard flashes its LEDs and sends its self-test byte ($AA). The
firmware ignores it.

| Measure | Probe | Expect (sim: `test_ps2_byte_received_and_keyboard_held`) |
|---|---|---|
| idle | KCLK J4 pin 36, KDATA J4 pin 37 | both high (4.7 k pull-ups R8, R9) |
| one key | KCLK | 11 clock pulses, 10–16.7 kHz (set by the keyboard); KDATA carries start 0, 8 data bits LSB first, odd parity, stop 1 |
| hold-off | KCLK after the 11th bit | **held low by U97 (74HC05)** until the CPU reads $5000; KREADY (U97 pin 1) high meanwhile. With the firmware polling, this lasts microseconds to a few ms. The sim's `A` key ($1C) arrives in KBD_DATA, KBD_STATUS & $0D = $09, and KCLK is released within 5 cycles of the read |
| timeout | U91 pin 9 (KTO_RC) | discharged by every KCLK low (D1), recharges through 47 k × 47 nF (about 2.2 ms); a frame cut short is dropped |

Press any key: the welcome screen gives way to the editor. Type a line: characters appear at
the cursor. F3 runs the example program. RESET returns to the editor with the text kept.
Firmware keyboard behaviour (scan code set 2, Shift, Caps Lock, Ctrl, F-keys) is covered by
`tests/test_firmware.py`.

## Stage 7 — EEPROM
Before inserting U90: **F4** shows "No EEPROM found". MISO has a pull-up (RN2), so an empty
socket reads $FF. Power off, insert **U90 (25LC512)**, power on.

| Measure | Probe | Expect |
|---|---|---|
| /CS | U90 pin 1 | high at idle and during reset (OUT2 OR RST) |
| SCK, MOSI, MISO | U90 pins 6, 5, 2 | 8-clock bursts at about 60 kHz (bit-banged), SPI mode 0, MSB first |
| /WP, /HOLD | U90 pins 3, 7 | 5 V |

* **F4**, slot 1: "Saved N bytes, slot 1." Every save is read back and compared before the
  firmware reports success. A 16 KB program takes about 6.5 s, a 1–2 KB one under a second.
* Power off and on, **F6**, slot 1, **Y**: the text is back. A 16 KB load takes about 2.7 s.
* Sim: `test_spi_to_eeprom` sends WREN, then RDSR, and reads back $02 (WEL set) through the
  netlist's OUT/IN ports. `tests/test_eeprom.py` (10 tests) covers the firmware's save,
  load, verify and no-chip paths against the chip model.

## Stage 8 — Run-in
* Run on USB-C power. Measure VCC at the far corner from J3 (for example J4 pin 39) under
  load. **If it falls below about 4.5 V, the MCP130 holds the machine in reset** (RST_N
  low). Use a shorter cable or a stronger supply.
* Leave the editor running for an hour, then F3 the examples (F5) and a save/load cycle.
* Try with JP1 open and fitted. The machine must work at full speed. If it works only at half
  speed, the board has a timing fault: the margins in doc 07 §3 assume AC parts in the 19
  AC positions.
* Record the final supply current, every stage's current, and any deviations from the
  tables above in this document.
