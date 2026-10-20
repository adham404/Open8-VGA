# Open8-VGA — Phase 6a: Parts Verification and Timing

Author: Adham Elshafei <adham_mohsen@outlook.com>
Status: **parts and timing budget complete; netlist verified at gate level and entered in HeyPCB.** Datasheet figures below were read from the vendors' own PDFs on 2026-10-19.
Stock figures are snapshots from distributor search results and must be re-checked before ordering.

## 1. Availability findings
| Part | Finding | Decision |
|---|---|---|
| SST39SF010A-70-4C-PHE (PDIP-32) | LCSC/JLCPCB: 0 stock since 2023. Farnell: 422 in stock. | Buy from Farnell/TME. Wire every ROM socket to the **SST39SF040 pinout** (pin 1 = A18, pin 30 = A17, unused high bits tied low), so 010A, 020A or 040 all fit. |
| SST39SF040-70-4C-PHE (ALU ROMs) | LCSC 0; DigiKey PDIP with a 17-week lead time; marketplace sellers only otherwise | **Long-lead item: order first** |
| CD74AC574E (pixel latch) | TI active; TME 56 in stock | OK |
| CD74ACT273E | TI active (AC273E being discontinued) | not needed after the redesign |
| AS6C62256-55PCN (main SRAM) | LCSC 8 in stock | OK |
| AS6C6264-55PCN (VRAM, font) | LCSC 0. Future Electronics 770 in stock, RS 64, DigiKey active (20-week lead time) | OK (fallback: AS6C62256) |
| 74AC161 (dot divider) | onsemi DIP obsolete; **TI CD74AC161E active**, about 1,600 at DigiKey | Use CD74AC161E |
| 74AC299 (pixel shifter) | **DIP obsolete** (onsemi); TI only makes HC299 | **Replace**: see §3 |
| 74HC574 | LCSC 74HC574N-HX, 490 in stock | OK |
| 25LC512-I/P | LCSC 318 in stock | OK |
| 25.175 MHz oscillator | ECS-100A-251.7, 5 V full-can DIP-14, about 1,160 at DigiKey | OK |

## 2. Datasheet timing (max; HC at VCC = 4.5 V, AC at 5 V ± 0.5 V; CL = 50 pF)
Read from the vendors' PDFs: TI CD74HCxxx/CD74ACxxx, Microchip DS20005022C (SST39SF0x0A),
Alliance AS6C62256 rev 1.2.

| Part | Parameter | 25 °C | −40…85 °C |
|---|---|---|---|
| 74HC574 | CLK → Q / OE → Q | 33 / 30 | 41 / 38 |
| 74HC377 | CLK → Q / setup | 38 / 12 | 48 / 15 |
| 74HC161/163 | CLK → Q / data and load setup / fMAX | 37 / 12 / 30 MHz | 46 / 15 / 24 MHz |
| 74HC138 | address → Y | 30 | 38 |
| 74HC139 | address → Y / enable → Y | 29 / 27 | 36 / 34 |
| 74HC154 | address → Y | 35 | 44 |
| 74HC157 | select → Y / data → Y | 29 / 25 | 36 / 31 |
| 74HC245 | A → B / enable | 22 / 30 | 28 / 38 |
| 74HC541 | data / enable | 23 / 32 | 29 / 40 |
| 74HC00, 08, 32 | A → Y | 18 | 23 |
| 74HC04 | A → Y | 17 | 21 |
| 74HC74 | CLK → Q | 35 | 44 |
| 74HC166 | fMAX / load setup | 30 MHz / 29 | 25 MHz / 36 |
| 74AC157 | select → Y / data → Y | — | 13.2 / 7.7 |
| 74AC245 | A → B / enable | — | 7.7 / 12.7 |
| 74AC161 | CLK → Q / fMAX | — | 15 / 103 MHz |
| 74AC151 | select → Y / data → Y | — | 16.5 / 12.3 |
| 74AC74 | CLK → Q / fMAX | — | 9.1 / 125 MHz |
| 74AC574 | CLK → Q / setup / OE | — | 11.3 / 2 / 14.5 |
| SST39SF0x0A-70 | tAA = tCE / tOE / tOHZ | 70 / 35 / 25 | same (0–70 °C part) |
| AS6C62256-55, AS6C6264-55 | tAA / tOE | 55 / 30 | same |

## 3. CPU timing budget at 3.147 MHz (cycle 317.8 ns, 8 dots of 39.7 ns)
Worst case (−40…85 °C column), measured from the rising CPU clock edge:

| Step | Path | Ready at |
|---|---|---|
| Control word | step counter 163 (46) + microcode flash tAA (70); IR and flags 377 (48) + 70 | **118 ns** |
| Bus source/destination decode | + 74HC154 (44) | 162 ns |
| Address select | + 74HC153 mux (≈ 36) after ASEL | ≈ 194 ns |
| Memory region decode | + 74HC138 (38) + gate (23) | 255 ns (74AC138: ≈ 227 ns) |
| Memory read data | max(address + tAA 70 = 264, region + tOE 35 = 290) | 290 ns |
| … into a 74HC377 | + setup 15 | **305 ns of 317.8: 13 ns margin** (74AC138: 41 ns) |
| ALU result | op bits 118 + ALU flash tAA 70 = 188; enabled at 198.6 + tOE 35 = 234 | 249 ns with setup |
| Flags | 188 + 74HC157 (31) + setup 15 | 234 ns |
| CPU read of VRAM (φ2) | 158.9 + AC157 13.2 + SRAM 55 + AC245 7.7 + setup 15 | 250 ns |

### Design changes forced by the budget
1. **No gated register clocks.** The planned `REGCLK = CLK OR /LOAD` needs the 74HC154
   decode settled before the clock's low half begins (158.9 ns). It settles at 162 ns, and a
   decoder transition inside the low half would create a false clock edge. All registers now
   share the CPU clock and use synchronous enables (74HC377 with /E, 74HC161/163 with
   /LOAD and ENP/ENT). A and B become 74HC377 + 74HC541 bus drivers (+2 chips).
2. **Address bus without tri-states.** PC, MAR, X and the stack address reach the address
   bus through 8 × 74HC153 (4-to-1) instead of tri-state drivers. Glitches on ASEL are then
   harmless: there is never contention on the address bus.
3. **Timed data-bus enables.** Each data-bus driver's /OE is ORed with /WIN, a window
   from dot 5.5 to dot 7.5 (218.5–298 ns). WIN and PH2 (dots 4.5–0.5) come from a 74AC574
   clocked on the falling dot clock, so they are glitch-free whatever the dot counter does.
   Decode glitches before 162 ns can no longer turn on two drivers, and the window closes
   one half-dot before the cycle edge, so the old driver is off before the next one starts.
   Bus capacitance (plus the 10 k keepers) holds the value through the edge.
4. **Write strobe** /WE = region · write · WIN (dots 5.5–7.5, ending 20 ns before the cycle
   edge, so address and data hold are met). That gives about 80 ns of pulse width for SRAM
   (tWP 45 ns) and covers the φ2 rule for VRAM and font RAM.
5. **Memory decoder in AC.** 74AC138 for the region decode raises the read margin from 13 ns
   to about 41 ns. With the later window (data enabled from dot 5.5) the worst-case path
   becomes WIN + tOE, leaving about 17 ns, so the AC138 is required; 74HC138 works only
   with the half-speed jumper.
6. **Half-speed jumper** stays as the hardware fallback: 1.57 MHz doubles every margin.

None of this changes the ISA, microcode, firmware or simulators. They model register-level
behaviour, which is identical.

## 4. Pixel serialiser (replaces the obsolete 74AC299)
* Font byte → **74AC574** (CD74AC574E) clocked at the character boundary: 11.3 ns.
* → **74AC151** 8-to-1 mux, select = dot counter Q2..Q0 from the 74AC161: data path 12.3 ns,
  select path 15 + 16.5 = 31.5 ns.
* → **74AC574** output register retimes the pixel (with BLANK, HSYNC and VSYNC) on the dot
  clock: 31.5 + setup ≈ 34 ns of 39.7 ns (≈ 5 ns margin at 85 °C; about 15 ns typical).
* The pixel then leaves one dot later than with a shift register. That is a fixed offset, so
  the timing ROM's BLANK and sync are unchanged.

## 5. Status
1. Netlist captured as code (`hardware/design.py`) and verified at gate level against the
   firmware (`tests/test_hardware.py`, 11 tests).
2. Schematic entered in HeyPCB (see `docs/08-board.md`).
