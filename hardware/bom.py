"""Bill of materials for the Open8-VGA Rev A board.

Built from the netlist (design.build()) and the KiCad mapping (kicad_map.py): identical parts
are grouped into one line with their reference list. IC sockets and jumper shunts, which are
not footprints on the board, follow as extra lines. The script also checks the BOM against
the routed board (every reference, footprint and value) and stops if they disagree.

    python3 hardware/bom.py [out.csv]      (default hardware/fab/rev-a/open8-vga-bom-revA.csv)

Author: Adham Elshafei
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)

import design     # noqa: E402
import kicad_map  # noqa: E402

PCB = os.path.join(ROOT, "kicad", "board", "open8-vga-motherboard.kicad_pcb")
OUT = os.path.join(ROOT, "hardware", "fab", "rev-a", "open8-vga-bom-revA.csv")

# Why each 74AC position is AC (docs/07-parts-timing.md). An HC part must not go here.
AC_WHY = {
    "74AC161": "dot counter at 25.175 MHz (74HC161 fMAX is 24 MHz at 85 C)",
    "74AC04": "clock / pixel-rate inverters",
    "74AC08": "CPU clock gate / pixel and colour gating",
    "74AC574": "dot-rate registers (phase, timing, pixel)",
    "74AC138": "memory region decode: read margin 13 ns with HC, about 41 ns with AC",
    "74AC157": "VRAM/font address mux on the CPU read path",
    "74AC245": "VRAM/font data buffer on the CPU read path",
    "74AC151": "pixel select at the dot rate",
}

DESC = {
    "74HC00": "quad 2-input NAND", "74HC02": "quad 2-input NOR", "74HC04": "hex inverter",
    "74AC04": "hex inverter", "74HC05": "hex inverter, open drain", "74HC08": "quad 2-input AND",
    "74AC08": "quad 2-input AND", "74HC11": "triple 3-input AND", "74HC14": "hex Schmitt inverter",
    "74HC32": "quad 2-input OR", "74HC86": "quad 2-input XOR", "74HC74": "dual D flip-flop",
    "74HC138": "3-to-8 decoder", "74AC138": "3-to-8 decoder", "74HC153": "dual 4-to-1 mux",
    "74HC154": "4-to-16 decoder (24-pin, 600 mil)", "74HC157": "quad 2-to-1 mux",
    "74AC157": "quad 2-to-1 mux", "74HC161": "4-bit binary counter, async clear",
    "74AC161": "4-bit binary counter, async clear", "74HC163": "4-bit binary counter, sync clear",
    "74HC164": "8-bit serial-in shift register", "74HC245": "octal bus transceiver",
    "74AC245": "octal bus transceiver", "74HC283": "4-bit adder", "74HC377": "octal register with enable",
    "74HC541": "octal tri-state buffer", "74HC574": "octal D register, tri-state",
    "74AC574": "octal D register, tri-state", "74AC151": "8-to-1 mux",
    "AS6C62256": "32K x 8 SRAM, 55 ns (28-pin, 600 mil)",
    "AS6C6264": "8K x 8 SRAM, 55 ns (28-pin, 600 mil)",
}

PASSIVE_DESC = {  # (kicad_map PASSIVE key) -> description
    "R": "resistor, 1/4 W metal film 1 %, axial",
    "C": "ceramic capacitor, 50 V X7R (C0G for 10n/47n fine), 5 mm lead pitch",
    "electrolytic": "aluminium electrolytic, >= 10 V, 10 mm dia, 5 mm pitch",
    "led": "LED 3 mm", "diode": "small-signal diode, DO-35",
    "tvs": "TVS diode 5 V unidirectional, SMB (surface mount)",
    "osc": "25.175 MHz 5 V full-can oscillator, DIP-14 outline",
    "supervisor": "reset supervisor, open drain, TO-92",
    "button": "tactile switch 6 x 6 mm, THT", "slide": "slide switch SPDT, THT",
    "jumper": "pin header 1x02, 2.54 mm", "pot": "trimmer 3/8 in square, top adjust",
    "555": "timer", "eeprom": "64 KiB SPI EEPROM", "npn": "NPN transistor, TO-92 (E-B-C)",
    "buzzer": "piezo transducer 12 mm, 7.6 mm pitch (passive, driven by Q1)",
    "polyfuse": "PTC resettable fuse, 1812 (surface mount)",
    "rnet": "resistor network, 8 resistors bussed, SIP-9",
    "minidin6": "6-pin mini-DIN socket (PS/2), THT", "de15": "DE-15 HD socket (VGA), right angle, THT",
    "usbc_power": "USB-C receptacle, power only 6P (SMD pads + THT shell tabs)",
    "header2x20": "pin header 2x20, 2.54 mm",
}

PASSIVE_MPN_BY_KEY = {  # suggestions where kicad_map has none, taken from the footprint names
    "slide": "C&K OS102011MS2QN1", "pot": "Bourns 3386P-1-105LF",
    "rnet": "Bourns 4609X-101-103LF", "usbc_power": "GCT USB4125-GF-A",
}

SMD = {"tvs", "polyfuse"}
LABELLED = {"jumper", "button", "slide", "led"}   # one physical part, values are labels
HYBRID = {"usbc_power"}


def natural(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2)))


def board_footprints(path=PCB):
    """{ref: (footprint, value)} read straight from the .kicad_pcb."""
    text = open(path).read()
    starts = [m.start() for m in re.finditer(r'\n\t\(footprint "', text)]
    out = {}
    for i, s in enumerate(starts):
        block = text[s:starts[i + 1] if i + 1 < len(starts) else len(text)]
        fp = re.search(r'\(footprint "([^"]+)"', block).group(1)
        ref = re.search(r'\(property "Reference" "([^"]+)"', block).group(1)
        val = re.search(r'\(property "Value" "([^"]+)"', block).group(1)
        out[ref] = (fp, val)
    return out


def dip_pins(fp):
    m = re.search(r"DIP-(\d+)_W([\d.]+)mm", fp)
    return (int(m.group(1)), "600 mil" if m.group(2) == "15.24" else "300 mil") if m else None


def rom_role(p):
    return {"U200": "firmware.bin"}.get(p.ref) or ("vga_timing.bin" if "timing" in p.note else None)


def build_lines(d):
    groups = {}
    for p in d.parts.values():
        pl = kicad_map.part_payload(p)
        if p.kind == "logic":
            key = ("logic", p.ptype, pl["mpn"])
        else:
            pkey = p.ptype if p.ptype in kicad_map.PASSIVE else p.ref.rstrip("0123456789")
            value = "" if pkey in LABELLED else p.value     # the value is only a label
            key = ("passive", pkey, value, pl["footprint"])
        groups.setdefault(key, []).append((p, pl))
    lines = []
    for key, items in groups.items():
        items.sort(key=lambda x: natural(x[0].ref))
        p0, pl0 = items[0]
        refs = [p.ref for p, _ in items]
        fp = pl0["footprint"]
        dip = dip_pins(fp)
        value = " / ".join(pl["value"] for _, pl in items) if key[1] in LABELLED else pl0["value"]
        row = {"qty": len(items), "refs": " ".join(refs), "value": value, "footprint": fp,
               "mpn": pl0.get("mpn") or "", "mount": "THT", "family": "", "socket": "", "notes": ""}
        if key[0] == "logic":
            ptype = key[1]
            row["package"] = "DIP-%d (%s)" % dip
            if ptype.startswith("74AC"):
                row["family"] = "AC (timing-critical)"
                row["notes"] = AC_WHY[ptype] + "; do not substitute HC"
            elif ptype.startswith("74HC"):
                row["family"] = "HC"
            if ptype == "SST39SF040":
                big = "040" in row["mpn"]
                row["description"] = ("4 Mbit (512K x 8) flash, 70 ns" if big
                                      else "1 Mbit (128K x 8) flash, 70 ns")
                row["socket"] = "required: 32-pin 600 mil"
                if big:
                    row["notes"] = ("ALU ROMs; U38 alu_r0.bin, U39 alu_r1.bin, U40 alu_f0.bin, "
                                    "U41 alu_f1.bin. Long lead time: order first")
                else:
                    roles = ["%s %s" % (p.ref, rom_role(p) or "ucode%s.bin" % p.note.split()[2])
                             for p, _ in items]
                    row["notes"] = ("; ".join(roles) + ". Socket is wired for the SST39SF040 "
                                    "pinout (A17/A18 low): 010A, 020A or 040 all fit")
            else:
                row["description"] = DESC[ptype]
                row["socket"] = "recommended: %d-pin %s" % dip
            if ptype == "74HC05":
                row["notes"] = "open-drain output holds the PS/2 clock; must be HC05/LS05 type"
        else:
            pkey = key[1]
            row["description"] = PASSIVE_DESC[pkey]
            row["package"] = fp.split(":")[1]
            if not row["mpn"]:
                row["mpn"] = PASSIVE_MPN_BY_KEY.get(pkey, "")
            if pkey in SMD:
                row["mount"] = "SMD"
            elif pkey in HYBRID:
                row["mount"] = "SMD + THT"
            if pkey in ("555", "eeprom"):
                row["package"] = "DIP-8 (300 mil)"
                row["socket"] = "recommended: 8-pin 300 mil"
            if pkey == "osc":
                row["socket"] = "optional: 14-pin 300 mil (4 corner pins used)"
            note = {
                "C": {"100n": "132 are decoupling (one per logic package, C7-C138); C1, C2 debounce "
                              "the STEP and CONTINUE buttons"}.get(p0.value, ""),
                "R": {"10k": "pull-ups/pull-downs (RSTRAW_N, HALF_EN, MCBANK, COLEN_R/G/B)",
                      "470": "R/G/B DAC into the monitor's 75 ohm: about 0.69 V full scale",
                      "100": "HSYNC/VSYNC series resistors", "5.1k": "USB-C CC pull-downs (5 V sink)",
                      "47k": "button debounce pull-ups, PS/2 timeout RC",
                      "4.7k": "PS/2 CLK and DATA pull-ups",
                      "1k": "555 timing, buzzer base, LED series"}.get(p0.value, ""),
                "jumper": "JP1 fit = half-speed CPU; JP2 fit = microcode bank 1; JP3-JP5 fit = colour on",
                "led": "D3 power, D4 HALT (lit while the CPU is halted); pad 1 = cathode",
                "button": "SW1 RESET, SW4 STEP, SW5 CONTINUE",
                "slide": "SW2 RUN/STEP, SW3 STEP/SLOW",
                "rnet": "pin 1 (dot) is the common pin, to VCC",
                "supervisor": "design note says MCP130T-450I/TO; the TO-92 part is MCP130-450DI/TO",
                "tvs": "cathode (band) to VCC",
                "polyfuse": "F2 = main 5 V input, F1 = keyboard supply",
                "usbc_power": "5 V input; shell tabs are plated holes",
                "electrolytic": "bulk on VCC; mind polarity",
                "diode": "cathode (band) to KCLK",
                "npn": "flat face per silkscreen; E = pad 1 (GND)",
                "header2x20": {"LOGIC": "J4 logic-analyser header", "EXPANSION": "J5 expansion"}.get(p0.value, ""),
                "osc": "pin 1 = sharp corner of the can",
            }.get(pkey, "")
            row["notes"] = note
        lines.append(row)
    order = {"U": 0, "X": 1, "C": 2, "R": 3, "RN": 4, "RV": 5, "D": 6, "Q": 7, "F": 8, "SW": 9,
             "JP": 10, "BZ": 11, "J": 12}

    def sort_key(r):
        first = r["refs"].split()[0]
        pre = natural(first)[0]
        ic = 0 if r["family"] or r["socket"].startswith("required") else 1
        return (order.get(pre, 20), ic, r["family"] != "HC", r["value"], natural(first))
    lines.sort(key=sort_key)
    return lines


SOCKET_MPN = {  # examples; check the datasheet and the board courtyard before ordering
    (32, "600 mil"): "Mill-Max 110-43-632-41-001000", (28, "600 mil"): "Mill-Max 110-43-628-41-001000",
    (24, "600 mil"): "Mill-Max 110-43-624-41-001000", (20, "300 mil"): "Mill-Max 110-43-320-41-001000",
    (16, "300 mil"): "Mill-Max 110-43-316-41-001000", (14, "300 mil"): "Mill-Max 110-43-314-41-001000",
    (8, "300 mil"): "Mill-Max 110-43-308-41-001000",
}


def socket_lines(d):
    by = {}
    for p in d.parts.values():
        if p.kind == "logic" or p.ptype in ("555", "eeprom"):
            fp = kicad_map.part_payload(p)["footprint"]
            by.setdefault(dip_pins(fp), []).append(p.ref)
    out = []
    for (pins, width), refs in sorted(by.items(), key=lambda x: (-x[0][0], x[0][1])):
        refs.sort(key=natural)
        need = "required" if pins == 32 else "recommended"
        out.append({"qty": len(refs), "refs": " ".join(refs), "value": "socket DIP-%d" % pins,
                    "description": "IC socket %d-pin %s (%s)" % (pins, width, need),
                    "family": "", "mpn": SOCKET_MPN[(pins, width)] + " (example)",
                    "package": "DIP-%d (%s)" % (pins, width), "footprint": "", "mount": "THT",
                    "socket": need,
                    "notes": ("flash chips are programmed off-board" if pins == 32 else
                              "lets the board be brought up in stages (docs/10-bring-up.md)")})
    out.append({"qty": 5, "refs": "JP1 JP2 JP3 JP4 JP5", "value": "shunt 2.54 mm",
                "description": "jumper shunt, 2.54 mm", "family": "", "mpn": "",
                "package": "", "footprint": "", "mount": "", "socket": "",
                "notes": "default: JP3-JP5 fitted (white), JP1 and JP2 open; see docs/09-assembly.md"})
    return out


def cross_check(d, board):
    problems = []
    for p in d.parts.values():
        pl = kicad_map.part_payload(p)
        if p.ref not in board:
            problems.append("%s not on the board" % p.ref)
        elif board[p.ref] != (pl["footprint"], pl["value"]):
            problems.append("%s: design %s/%s, board %s/%s" % ((p.ref, pl["footprint"], pl["value"])
                                                             + board[p.ref]))
    problems += ["%s on the board but not in design.py" % r for r in sorted(set(board) - set(d.parts))]
    return problems


FIELDS = ["item", "qty", "refs", "value", "description", "family", "mpn", "package", "mount",
          "socket", "footprint", "notes"]


def main(out=OUT):
    d = design.build()
    board = board_footprints()
    problems = cross_check(d, board)
    if problems:
        sys.exit("BOM does not match the board:\n  " + "\n  ".join(problems))
    lines = build_lines(d)
    placed = sum(r["qty"] for r in lines)
    assert placed == len(d.parts) == len(board), (placed, len(d.parts), len(board))
    extra = socket_lines(d)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, r in enumerate(lines + extra, 1):
            w.writerow(dict(r, item=i))
    logic = sum(1 for p in d.parts.values() if p.kind == "logic")
    print("%s: %d lines for %d placed parts (%d logic packages), board has %d footprints: all "
          "references, footprints and values match; plus %d socket/shunt lines (%d items)"
          % (os.path.relpath(out, ROOT), len(lines), placed, logic, len(board), len(extra),
             sum(r["qty"] for r in extra)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else OUT)
