# 08 — Schematic and board

Author: Adham Elshafei

Status: **Rev A routed on 6 layers in KiCad; DRC clean (0 errors, 0 unconnected); Gerbers made.**
Board: `kicad/board/open8-vga-motherboard.kicad_pcb`. Fabrication files: `hardware/fab/rev-a/open8-vga-gerbers-revA.zip`.
HeyPCB project (private to the author): "Open8-VGA motherboard". The routed board of record is the KiCad project above.

## 1. Source of truth
The netlist lives as code in `hardware/design.py`. Everything downstream is generated from it:

| Step | Tool | Output |
|---|---|---|
| Netlist | `hardware/design.py` (`build()`) | 322 parts, 526 nets, 2,712 connected pins |
| Static checks | `hardware/gatesim.py` (`check()`) | 0 problems |
| Gate-level simulation | `tests/test_hardware.py` | 11 tests: every instruction form, firmware boot, video, PS/2, SPI |
| KiCad mapping | `hardware/kicad_map.py` | `build/heypcb/parts_*.json`, `nets_*.json` |
| Schematic and board | HeyPCB (`add_parts`, `connect`) | project 813a82d931bd |

To change the board, edit `design.py`, re-run the tests, regenerate with
`python3 hardware/kicad_map.py`, and push the changed parts and nets to HeyPCB.

## 2. Parts
132 logic packages, all DIP, all socketable. The nine flash chips use 32-pin sockets so they
can be programmed off-board.

| Sheet | Logic packages | Contents |
|---|---|---|
| clock | 14 | 25.175 MHz oscillator, dot counter, WIN/PH2 register, RUN/STEP/HALT, 555 slow clock |
| control | 15 | IR, step counter, 3 microcode flash, source/destination decoders |
| datapath | 35 | A, B, L, T, SP, X, PC, MAR, flags, 4 ALU flash |
| memory | 10 | 128 KiB firmware flash (16 KiB window + banks), 32 KiB SRAM, region decode, write protection |
| io | 15 | OUT port, input port, EEPROM (25LC512), buzzer, scroll registers |
| keyboard | 12 | PS/2 receiver with inhibit and timeout |
| video | 31 | H/V counters, timing ROM, VRAM, font RAM, pixel path |

Plus 138 × 100 nF decoupling (one per package and extra for the memories), a 470 µF bulk
capacitor, the USB-C power entry (5.1 kΩ CC pull-downs, 2 A polyfuse, SMBJ5.0A TVS), the
MCP130 reset supervisor, and the RUN/STEP, STEP/SLOW, RESET, STEP and CONTINUE controls.

### Symbol and footprint choices
* 74HC/AC parts use the KiCad `74xx:74LSxxx` symbols. Every pin table was checked
  against the datasheet-derived tables in `hardware/lib.py`. The 74LS163 symbol is single-source
  in HeyPCB, so it was compared pin by pin with the 74HC163 table: identical.
* **PS/2 jack (J1):** CUI MD-60SM (LCSC C22359735). KiCad has no mini-DIN land, so HeyPCB
  converted the catalogue's footprint (`HeyPCB_LCSC:DC-IN-TH_MD-60SM`). Pads 1–6 follow the
  standard mini-DIN numbering (1 DATA, 3 GND, 4 +5 V, 5 CLK); pads 7–9 are the shield, tied to
  GND.
* **VGA (J2):** `Connector_Dsub:DSUB-15-HD_Socket_Horizontal_P2.29x1.90mm_…`.
* **Q1:** `Transistor_BJT:Q_NPN_EBC` (2N3904, TO-92).

## 3. Netlist checks
* HeyPCB's net and pin totals match the local netlist exactly (526 nets, 2,712 pins), and no
  pin was rejected.
* Entering the netlist surfaced one real bug: the video adder's carry net and the USB-C CC1
  pin were both named `CC1`, which would have joined them. The USB nets are now `USB_CC1` and
  `USB_CC2`. `gatesim.check()` now refuses any signal net that joins the power-entry sheet to
  the logic (only `HALTED`, which drives the HALT LED, is allowed).
* Unused microcode bits MC22 and MC23 are single-pin nets on purpose (spare control bits).

## 4. Placement and routing (2026-10-19)
* HeyPCB's electrical gate asked for an SPI bus it could recognise, so the EEPROM nets are
  named `EE_SCK`, `EE_MOSI`, `EE_CS_N` (they are OUT_PORT bits 0 and 1 and the OR-gated
  OUT2), with `MISO` unchanged. Tests updated; all 11 pass.
* Placement: automatic, outline 294 × 250 mm. Connectors on the left edge; the 2×20 headers
  and jumpers sit about 15 mm in from the edge, which is fine for them.
* Routing on 2 layers: one 25-minute job routed 724 of 2,196 connections (1,472 still open).
  VCC and GND alone account for roughly 900 connections, so the board needs inner power
  planes (4 layers) to route.
* 4 layers (JLCPCB rules: 0.127 mm track/clearance, 0.45/0.30 mm vias). The first
  4-layer job built on the 2-layer copper and stalled (no change, not charged). After a full
  rip-up, with VCC and GND at 0.5 mm (the inner planes will carry the current; they can only
  be poured once routing is complete) and VBUS at 1 mm, a fresh job routed 276 of 2,196
  connections in its time budget (1,920 open).
* The router's 25-minute cap is the limit on a board this size (2,887 pads), and the
  automatic placement leaves many long nets (the dot clock spans about 200 mm, the
  microcode-to-decoder nets about 180 mm). Spend so far: placement $0.05, routing $2.
* ERC: HeyPCB's engine failed three times on this board size (not charged). The local
  `gatesim.check()` and gate-level tests cover the electrical rules in the meantime.

## 5. Local KiCad layout (2026-10-20)
HeyPCB cannot import routed copper, so the board is finished in KiCad from HeyPCB's export
(`kicad/board/`). The exported netlist was checked pin by pin against `design.py`: 2,712
pins, 0 mismatches.

* **Grouped placement** (`hardware/layout/place.py`): slot rows (wide DIPs on top, narrow
  DIPs below, discretes in a left strip by the edge connectors), each decoupling capacitor
  above its chip, simulated annealing on signal wirelength (clock nets weighted 3x).
  Total signal wirelength 83.1 m -> 52.1 m, clock nets 3.1 m -> 1.9 m; board 313 x 259.5 mm.
  KiCad DRC after placement: no courtyard or clearance errors.
* **Routing** with Freerouting 2.5 (native CLI, run one pass at a time by
  `hardware/layout/route_loop.sh`; its between-pass snapshot crashes the native build).
  Rules: 0.2 mm signals / 0.15 mm clearance, via-to-via 0.35 mm (JLCPCB 0.5 mm hole-to-hole).
  * Signals allowed on all 4 layers: 50 connections left after 10 passes, but most copper
    ended up on the inner layers, leaving no room for planes.
  * Signals on top and bottom only, inner layers kept for GND and VCC planes: 1,268 ->
    384 -> 244 open after two passes; the third pass oscillated on the data bus and was
    stopped. Two signal layers are not enough at this density.

## 6. Six-layer board, Rev A (2026-10-20)
Four signal layers plus two solid planes route this design; four layers do not (section 5).

| Layer | Use |
|---|---|
| F.Cu | signals |
| In1.Cu | **GND plane** (one solid pour) |
| In2.Cu | signals |
| In3.Cu | signals |
| In4.Cu | **VCC plane** (one solid pour) |
| B.Cu | signals |

**Flow** (all scripts in `hardware/layout/`, run in this order):
1. `place.py` and `apply.py`: grouped placement (section 5).
2. `route_loop.sh`: Freerouting one pass at a time, with `dsn_fix.py` hiding the two plane
   layers and the VCC/GND nets (Freerouting 2.5's native CLI crashes on declared planes, so the
   planes are poured in KiCad afterwards). 13 passes: 1,268 -> 27 open.
3. The 22 nets that had spilled onto the VCC layer were ripped up and re-routed on the four
   signal layers with 0.127 mm track and gap (`DSN_DEFAULT_RULE=127,127`); 6 more passes.
4. `maze.py`: a grid A* router finished the last 11 connections Freerouting could not place
   (0.1 mm grid, full via and hole-to-hole clearances).
5. `tidy.py`: all vias through (F.Cu to B.Cu), import stubs removed, neck-downs widened to
   0.127 mm where clearance allows.
6. `planes.py`: GND and VCC pours; the six surface-mount power pads (F1, F2, D2, USB-C GND)
   get a 0.5 mm track and a via placed clear of all other copper; the VGA connector's GND pins
   connect solid (its 2.29 mm pitch leaves no room for thermal spokes).
7. `silk.py`: reference labels centred on each part at 1.0 mm / 0.16 mm (JLCPCB minimums);
   credits "Open8-VGA / Designed by Adham Elshafei / adham_mohsen@outlook.com / 2026" on the
   front and "©2026 Adham Elshafei — Rev A" on the back.

**Result**
* 313 x 259.5 mm, 6 layers, 1.6 mm. 626 through vias (0.45/0.30 mm), 3,501 plated holes.
* KiCad DRC: 0 errors, 0 unconnected. 77 silkscreen warnings remain (labels touching pads or
  each other; JLCPCB clips silkscreen off exposed copper).
* Rules: signals 0.2 mm (0.127 mm on the 22 re-routed nets), clearance 0.127 mm, VCC/GND
  0.5 mm, VBUS 1 mm, via-to-via 0.35 mm (0.5 mm hole-to-hole). 16 short tracks stay at
  0.090-0.095 mm where widening would break clearance; the board minimum is set to 0.09 mm,
  JLCPCB's limit for multilayer boards. These are the tightest spots on the board.
* Gerbers (13 layers), Excellon drill (plated/non-plated separate) and drill maps:
  `build/gerbers/`, zipped as `hardware/fab/rev-a/open8-vga-gerbers-revA.zip`.

**HeyPCB** keeps the schematic and parts (project 813a82d931bd) but not this layout: it has no
way to import routed copper, so its board still shows the earlier 4-layer attempt.

## 7. Build documentation and next steps
* **BOM:** `hardware/fab/rev-a/open8-vga-bom-revA.csv`, generated by `python3 hardware/bom.py` from
  `design.build()` and `kicad_map.py`. It has 66 part lines covering the 322 placed parts,
  plus sockets and jumper shunts. Before writing, the script checks every reference,
  footprint and value against the routed board (322 of 322 match). It marks the 19
  timing-critical 74AC positions and gives each flash socket its ROM image.
* **Assembly:** [09-assembly.md](09-assembly.md) covers the soldering order, which ROM image
  goes in which socket (with checksums), the jumper and switch settings, and connector pinouts.
* **Bring-up:** [10-bring-up.md](10-bring-up.md) is a staged plan: power, clock, video sync,
  CPU single-step, firmware boot, keyboard, EEPROM. Each stage lists its chips and the values
  the simulator predicts.

Still to do:
1. Review the board in KiCad before ordering (open `kicad/board/open8-vga-motherboard.kicad_pro`).
2. Order (the SST39SF040 ALU ROMs first: long lead time), assemble, and bring up following
   docs 09 and 10.
