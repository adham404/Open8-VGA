"""Open8-VGA motherboard netlist, as code.

Every chip, every connection. `build()` returns a Design: parts (with pin -> net maps) and
nets. The same object feeds the gate-level simulator (gatesim.py), the netlist checks and
the HeyPCB schematic entry. Signal names: D0-D7 data bus, A0-A15 address bus, MC0-MC23 the
microinstruction, *_N = active low. Timing choices are explained in docs/07-parts-timing.md.
Author: Adham Elshafei
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import lib  # noqa: E402

REF_ROM, REF_RAM, REF_VRAM, REF_FONT = "U200", "U201", "U202", "U203"

GATE_TYPES = {  # function -> (package type per family, unit pin names)
    "nand": ("74HC00", ("A", "B", "Y"), 4),
    "nor": ("74HC02", ("A", "B", "Y"), 4),
    "and": ("74HC08", ("A", "B", "Y"), 4),
    "or": ("74HC32", ("A", "B", "Y"), 4),
    "xor": ("74HC86", ("A", "B", "Y"), 4),
    "inv": ("74HC04", ("A", "Y"), 6),
    "and3": ("74HC11", ("A", "B", "C", "Y"), 3),
    "schmitt": ("74HC14", ("A", "Y"), 6),
    "inv_od": ("74HC05", ("A", "Y"), 6),
    "ac_and": ("74AC08", ("A", "B", "Y"), 4),
    "ac_inv": ("74AC04", ("A", "Y"), 6),
}


def bus(name, n, start=0):
    return ["%s%d" % (name, i) for i in range(start, start + n)]


class PartInst:
    def __init__(self, ref, ptype, sheet, value=None, conn=None, kind="logic", pins=None, note=""):
        self.ref, self.ptype, self.sheet = ref, ptype, sheet
        self.value = value or ptype
        self.conn = dict(conn or {})        # pin name -> net
        self.kind = kind                    # logic | passive
        self.pins = pins                    # passive parts: {pin number: net}
        self.note = note


class Design:
    def __init__(self):
        self.parts = {}
        self.pools = {}
        self.counters = {}
        self.sheet = "misc"
        self.pullups = {}                   # net -> "up" / "down" (resistor to VCC / GND)

    # ---------------------------------------------------------------- creation
    def next_ref(self, prefix):
        while True:
            self.counters[prefix] = self.counters.get(prefix, 0) + 1
            ref = "%s%d" % (prefix, self.counters[prefix])
            if ref not in self.parts:
                return ref

    def chip(self, ptype, conn, ref=None, note=""):
        ref = ref or self.next_ref("U")
        pins = lib.TYPES[ptype][0]
        for p in conn:
            if p not in pins:
                raise KeyError("%s %s has no pin %s" % (ref, ptype, p))
        self.parts[ref] = PartInst(ref, ptype, self.sheet, conn=conn, note=note)
        return ref

    ZONES = {"clock": "cpu", "control": "cpu", "datapath": "cpu", "memory": "cpu", "io": "cpu",
             "keyboard": "video", "video": "video"}

    def gate(self, func, *nets):
        """Allocate one gate unit (gates are pooled per board zone). nets = inputs..., output."""
        ptype, names, units = GATE_TYPES[func]
        pool = self.pools.setdefault((ptype, self.ZONES.get(self.sheet, self.sheet)), [])
        if not pool or pool[-1][1] >= units:
            ref = self.chip(ptype, {})
            pool.append([ref, 0])
        ref, used = pool[-1]
        unit = used + 1
        pool[-1][1] = unit
        for name, net in zip(names, nets):
            self.parts[ref].conn["%d%s" % (unit, name)] = net
        return ref

    def passive(self, prefix, value, pins, ptype="passive", note=""):
        ref = self.next_ref(prefix)
        self.parts[ref] = PartInst(ref, ptype, self.sheet, value=value, kind="passive",
                                   pins=dict(pins), note=note)
        return ref

    def pull(self, net, direction="up", value="10k"):
        self.pullups[net] = direction
        self.passive("R", value, {1: net, 2: "VCC" if direction == "up" else "GND"},
                     note="pull-%s" % direction)

    def finalize(self):
        """Tie the inputs of spare gates to GND (CMOS inputs must not float)."""
        gate_types = {t[0] for t in GATE_TYPES.values()}
        for p in self.parts.values():
            if p.kind == "logic" and p.ptype in gate_types:
                for name in lib.TYPES[p.ptype][0]:
                    if name not in p.conn and not name.endswith("Y"):
                        p.conn[name] = "GND"

    # ---------------------------------------------------------------- queries
    def nets(self):
        out = {}
        for p in self.parts.values():
            if p.kind == "logic":
                pins = lib.TYPES[p.ptype][0]
                for name, net in p.conn.items():
                    out.setdefault(net, []).append((p.ref, pins[name], name))
                vcc, gnd = lib.TYPES[p.ptype][1], lib.TYPES[p.ptype][2]
                out.setdefault("VCC", []).append((p.ref, vcc, "VCC"))
                out.setdefault("GND", []).append((p.ref, gnd, "GND"))
            else:
                for num, net in p.pins.items():
                    out.setdefault(net, []).append((p.ref, num, str(num)))
        return out


def build():
    d = Design()
    M = bus("MC", 24)
    DB = bus("D", 8)
    AB = bus("A", 16)

    # ================================================================ clock & phases
    d.sheet = "clock"
    d.passive("X", "25.175MHz", {1: "VCC", 7: "GND", 8: "DOTCLK", 14: "VCC"},
              ptype="osc", note="ECS-100A-251.7 full-can oscillator")
    d.chip("74AC161", {"CLK": "DOTCLK", "CLR": "VCC", "LOAD": "VCC", "ENP": "VCC", "ENT": "VCC",
                       "A": "GND", "B": "GND", "C": "GND", "D": "GND",
                       "QA": "DOT0", "QB": "DOT1", "QC": "DOT2"},
           note="dot counter: 8 dots per character")
    d.gate("ac_inv", "DOT2", "CHARCLK")                 # rises at dot 0 (char boundary)
    d.gate("ac_inv", "DOTCLK", "DOTCLK_N")
    # Phase signals are decoded from the (stable) dot count and registered in the middle of
    # each dot, so they are glitch-free and change only at half-dot boundaries.
    d.gate("xor", "DOT0", "DOT1", "DOTX")
    d.gate("and", "DOT2", "DOTX", "WINRAW")             # dots 5 and 6
    d.chip("74AC574", {"CLK": "DOTCLK_N", "OE": "GND",
                       "D1": "WINRAW", "D2": "DOT2", "D3": "GND",
                       "D4": "GND", "D5": "GND", "D6": "GND", "D7": "GND", "D8": "GND",
                       "Q1": "WIN", "Q2": "PH2"},
           note="phase register: WIN dots 5.5-7.5 (bus drive and write), PH2 4.5-0.5")
    d.gate("inv", "WIN", "WIN_N")
    # reset: MCP130 supervisor (open drain) + button, synchronised to the character clock
    d.passive("U", "MCP130-450", {1: "RSTRAW_N", 2: "VCC", 3: "GND"}, ptype="supervisor",
              note="MCP130T-450I/TO, open-drain reset")
    d.pull("RSTRAW_N", "up")
    d.passive("SW", "RESET", {1: "RSTRAW_N", 2: "GND"}, ptype="button")
    ffr = d.chip("74HC74", {"1CLK": "CHARCLK", "1D": "RSTRAW_N", "1CLR": "VCC", "1PRE": "VCC",
                            "1Q": "RST_N",
                            "2CLK": "CHARCLK", "2D": "TOG_N", "2CLR": "VCC", "2PRE": "VCC",
                            "2Q": "TOG", "2QN": "TOG_N"})
    d.gate("inv", "RST_N", "RST")
    # clock modes: RUN, STEP (button), SLOW (555), HALT, half speed
    d.passive("SW", "RUN/STEP", {1: "VCC", 2: "STEP_MODE", 3: "GND"}, ptype="slide")
    d.passive("SW", "STEP/SLOW", {1: "VCC", 2: "SLOW_SEL", 3: "GND"}, ptype="slide")
    d.passive("SW", "STEP", {1: "STEPBTN_RC", 2: "GND"}, ptype="button")
    d.pull("STEPBTN_RC", "up", "47k")
    d.passive("C", "100n", {1: "STEPBTN_RC", 2: "GND"})
    d.gate("schmitt", "STEPBTN_RC", "STEPBTN")          # high while pressed
    d.passive("SW", "CONTINUE", {1: "CONTBTN_RC", 2: "GND"}, ptype="button")
    d.pull("CONTBTN_RC", "up", "47k")
    d.passive("C", "100n", {1: "CONTBTN_RC", 2: "GND"})
    d.gate("schmitt", "CONTBTN_RC", "CONT")
    d.gate("schmitt", "CONT", "CONT_N")
    d.passive("U", "NE555", {1: "GND", 2: "T555", 3: "SLOWCLK", 4: "VCC", 5: "CTRL555",
                             6: "T555", 7: "D555", 8: "VCC"}, ptype="555",
              note="astable 1-200 Hz: R 1k + 1M pot, C 1uF")
    d.passive("R", "1k", {1: "VCC", 2: "D555"})
    d.passive("RV", "1M", {1: "D555", 2: "T555", 3: "T555"}, ptype="pot")
    d.passive("C", "1u", {1: "T555", 2: "GND"})
    d.passive("C", "10n", {1: "CTRL555", 2: "GND"})
    d.passive("JP", "HALF", {1: "HALF_EN", 2: "VCC"}, ptype="jumper")
    d.pull("HALF_EN", "down")
    d.chip("74HC157", {"S": "SLOW_SEL", "G": "GND", "1A": "STEPBTN", "1B": "SLOWCLK",
                       "1Y": "STEPSRC", "2A": "GND", "2B": "GND", "3A": "GND", "3B": "GND",
                       "4A": "GND", "4B": "GND"})
    d.chip("74HC74", {"1CLK": "CHARCLK", "1D": "STEPSRC", "1CLR": "VCC", "1PRE": "VCC", "1Q": "STEPSYNC1",
                      "2CLK": "CHARCLK", "2D": "STEPSYNC1", "2CLR": "VCC", "2PRE": "VCC",
                      "2QN": "STEPSYNC2_N"})
    d.gate("and", "STEPSYNC1", "STEPSYNC2_N", "PULSE")
    d.gate("inv", "STEP_MODE", "RUN")
    d.gate("inv", "HALF_EN", "HALF_N")
    d.gate("or", "TOG", "HALF_N", "HALFOK")
    d.gate("and", "RUN", "HALTED_N", "RUNOK")
    d.gate("and", "RUNOK", "HALFOK", "CE_RUN")
    d.gate("and", "STEP_MODE", "PULSE", "CE_STEP")
    d.gate("or", "CE_RUN", "CE_STEP", "CE_ANY")
    d.gate("or", "CE_ANY", "RST", "CE_RAW")
    d.gate("and", "CONT_N", "RST_N", "HCLR_N")
    d.gate("or", M[19], "HALTED", "HALT_D")
    d.chip("74HC74", {"1CLK": "DOT2", "1D": "CE_RAW", "1CLR": "VCC", "1PRE": "VCC", "1Q": "CE_L",
                      "2CLK": "CPUCLK", "2D": "HALT_D", "2CLR": "HCLR_N", "2PRE": "VCC",
                      "2Q": "HALTED", "2QN": "HALTED_N"}, note="clock-enable latch, HALT latch")
    d.gate("ac_and", "CHARCLK", "CE_L", "CPUCLK")

    # ================================================================ control unit
    d.sheet = "control"
    mc_addr = (["FLAG_C", "FLAG_Z", "FLAG_N", "FLAG_V"] + bus("STEP", 4) + bus("IR", 8)
               + ["MCBANK", "GND", "GND"])
    for k in range(3):
        conn = {"A%d" % i: mc_addr[i] for i in range(19)}
        conn.update({"DQ%d" % i: M[8 * k + i] for i in range(8)})
        conn.update({"CE": "GND", "OE": "GND", "WE": "VCC"})
        d.chip("SST39SF040", conn, note="microcode ROM %d (SST39SF010A in a 040-wired socket)" % k)
    d.passive("JP", "MCBANK", {1: "MCBANK", 2: "VCC"}, ptype="jumper")
    d.pull("MCBANK", "down")
    d.gate("nor", M[18], "RST", "STEPCLR_N")
    d.chip("74HC163", {"CLK": "CPUCLK", "CLR": "STEPCLR_N", "LOAD": "VCC", "ENP": "VCC",
                       "ENT": "VCC", "A": "GND", "B": "GND", "C": "GND", "D": "GND",
                       "QA": "STEP0", "QB": "STEP1", "QC": "STEP2", "QD": "STEP3"},
           note="microstep counter")
    d.chip("74HC377", dict({"E": "LD_IR_N", "CP": "CPUCLK"},
                           **{"D%d" % (i + 1): DB[i] for i in range(8)},
                           **{"Q%d" % (i + 1): "IR%d" % i for i in range(8)}), note="IR")
    src = ["NONE", "A", "B", "ALU", "MEM", "XL", "XH", "SP", "PCL", "PCH", "FLAGS"]
    conn = {"A": M[0], "B": M[1], "C": M[2], "D": M[3], "G1": "GND", "G2": "GND"}
    for i, s in enumerate(src[1:], 1):
        conn["Y%d" % i] = "SRC_%s_N" % s
    d.chip("74HC154", conn, note="bus source decoder (raw)")
    dst = ["NONE", "A", "B", "T", "L", "IR", "MARL", "MARH", "XL", "XH", "SP", "WR", "FLAGSBUS"]
    conn = {"A": M[4], "B": M[5], "C": M[6], "D": M[7], "G1": "GND", "G2": "GND"}
    for i, s in enumerate(dst[1:], 1):
        conn["Y%d" % i] = ("LD_%s_N" % s) if s not in ("WR",) else "WR_N"
    d.chip("74HC154", conn, note="bus destination decoder")
    for s in ["A", "B", "ALU", "XL", "XH", "SP", "PCL", "PCH", "FLAGS"]:
        d.gate("or", "SRC_%s_N" % s, "WIN_N", "OE_%s_N" % s)
    d.gate("or", "SRC_MEM_N", "WIN_N", "RD_N")
    d.gate("inv", "LD_FLAGSBUS_N", "FLAGSBUS")
    d.gate("nor", M[17], "FLAGSBUS", "FLAGLD_N")
    for k in range(2):                                  # flag source: ALU ROM 0/1 or bus
        conn = {"A": M[11], "B": "FLAGSBUS", "1G": "GND", "2G": "GND"}
        for u, bit in ((1, 2 * k), (2, 2 * k + 1)):
            conn.update({"%dC0" % u: "AF0_%d" % bit, "%dC1" % u: "AF1_%d" % bit,
                         "%dC2" % u: DB[bit], "%dC3" % u: DB[bit], "%dY" % u: "FN%d" % bit})
        d.chip("74HC153", conn)
    flags = ["FLAG_C", "FLAG_Z", "FLAG_N", "FLAG_V"]
    conn = {"E": "FLAGLD_N", "CP": "CPUCLK"}
    for i in range(8):
        conn["D%d" % (i + 1)] = "FN%d" % i if i < 4 else "GND"
    for i in range(4):
        conn["Q%d" % (i + 1)] = flags[i]
    d.chip("74HC377", conn, note="FLAGS (0000VNZC)")
    conn = {"OE1": "OE_FLAGS_N", "OE2": "GND"}
    for i in range(8):
        conn["A%d" % (i + 1)] = flags[i] if i < 4 else "GND"
        conn["Y%d" % (i + 1)] = DB[i]
    d.chip("74HC541", conn, note="FLAGS -> bus")

    # ================================================================ datapath
    d.sheet = "datapath"

    def reg377(enable, q, note, clock="CPUCLK"):
        conn = {"E": enable, "CP": clock}
        for i in range(8):
            conn["D%d" % (i + 1)] = DB[i]
            conn["Q%d" % (i + 1)] = q[i]
        return d.chip("74HC377", conn, note=note)

    def drv541(inputs, oe, note, outs=DB):
        conn = {"OE1": oe, "OE2": "GND"}
        for i in range(8):
            conn["A%d" % (i + 1)] = inputs[i]
            conn["Y%d" % (i + 1)] = outs[i]
        return d.chip("74HC541", conn, note=note)

    reg377("LD_A_N", bus("AQ", 8), "register A")
    drv541(bus("AQ", 8), "OE_A_N", "A -> bus")
    reg377("LD_B_N", bus("BQ", 8), "register B")
    drv541(bus("BQ", 8), "OE_B_N", "B -> bus")
    reg377("LD_L_N", bus("LQ", 8), "ALU operand L")
    reg377("LD_T_N", bus("TQ", 8), "ALU operand T")
    alu_addr = [M[8], M[9], M[10]] + bus("TQ", 8) + bus("LQ", 8)
    d.gate("or", "OE_ALU_N", M[11], "OE_AR0_N")
    d.gate("inv", M[11], "ALUOP3_N")
    d.gate("or", "OE_ALU_N", "ALUOP3_N", "OE_AR1_N")
    for name, oe, outs in (("result 0-7", "OE_AR0_N", DB), ("result 8-15", "OE_AR1_N", DB),
                           ("flags 0-7", "GND", bus("AF0_", 4)), ("flags 8-15", "GND", bus("AF1_", 4))):
        conn = {"A%d" % i: alu_addr[i] for i in range(19)}
        conn.update({"DQ%d" % i: outs[i] for i in range(len(outs))})
        conn.update({"CE": "GND", "OE": oe, "WE": "VCC"})
        d.chip("SST39SF040", conn, note="ALU ROM, ops %s" % name)
    # X: 4 x 74HC161, loads from the data bus, counts on X_INC
    x = bus("X", 16)
    carry = M[16]
    for k in range(4):
        load = "LD_XL_N" if k < 2 else "LD_XH_N"
        dsrc = DB[0:4] if k % 2 == 0 else DB[4:8]
        conn = {"CLK": "CPUCLK", "CLR": "VCC", "LOAD": load, "ENP": M[16], "ENT": carry,
                "A": dsrc[0], "B": dsrc[1], "C": dsrc[2], "D": dsrc[3],
                "QA": x[4 * k], "QB": x[4 * k + 1], "QC": x[4 * k + 2], "QD": x[4 * k + 3]}
        if k < 3:
            conn["RCO"] = "XC%d" % k
            carry = "XC%d" % k
        d.chip("74HC161", conn, note="X bits %d-%d" % (4 * k, 4 * k + 3))
    drv541(x[0:8], "OE_XL_N", "XL -> bus")
    drv541(x[8:16], "OE_XH_N", "XH -> bus")
    # PC: 4 x 74HC163, loads from the address bus
    p = bus("P", 16)
    d.gate("nor", M[20], "RST", "PCCLR_N")
    d.gate("inv", M[15], "PCLOAD_N")
    carry = M[14]
    for k in range(4):
        conn = {"CLK": "CPUCLK", "CLR": "PCCLR_N", "LOAD": "PCLOAD_N", "ENP": M[14], "ENT": carry,
                "A": AB[4 * k], "B": AB[4 * k + 1], "C": AB[4 * k + 2], "D": AB[4 * k + 3],
                "QA": p[4 * k], "QB": p[4 * k + 1], "QC": p[4 * k + 2], "QD": p[4 * k + 3]}
        if k < 3:
            conn["RCO"] = "PC%d" % k
            carry = "PC%d" % k
        d.chip("74HC163", conn, note="PC bits %d-%d" % (4 * k, 4 * k + 3))
    drv541(p[0:8], "OE_PCL_N", "PCL -> bus")
    drv541(p[8:16], "OE_PCH_N", "PCH -> bus")
    reg377("LD_MARL_N", bus("M", 8), "MAR low")
    reg377("LD_MARH_N", bus("M", 8, 8), "MAR high")
    reg377("LD_SP_N", bus("S", 8), "SP")
    drv541(bus("S", 8), "OE_SP_N", "SP -> bus")
    stack_hi = [1, 1, 1, 1, 0, 1, 0, 1]                 # $AF
    spaddr = bus("S", 8) + ["VCC" if v else "GND" for v in stack_hi]
    m = bus("M", 16)
    for k in range(8):                                  # address bus: 4-to-1 per bit
        conn = {"A": M[12], "B": M[13], "1G": "GND", "2G": "GND"}
        for u, bit in ((1, 2 * k), (2, 2 * k + 1)):
            conn.update({"%dC0" % u: p[bit], "%dC1" % u: m[bit], "%dC2" % u: x[bit],
                         "%dC3" % u: spaddr[bit], "%dY" % u: AB[bit]})
        d.chip("74HC153", conn, note="address bits %d-%d" % (2 * k, 2 * k + 1))
    d.passive("RN", "10k", {1: "VCC", **{i + 2: DB[i] for i in range(8)}}, ptype="rnet",
              note="data bus pull-ups (9-pin SIP)")
    for net in DB:
        d.pullups[net] = "up"

    # ================================================================ memory & decode
    d.sheet = "memory"
    d.chip("74AC138", {"A": AB[12], "B": AB[13], "C": AB[14], "G2A": AB[15], "G2B": "GND",
                       "G1": "VCC", "Y0": "RG0_N", "Y1": "RG1_N", "Y2": "RG2_N", "Y3": "RG3_N",
                       "Y4": "RG4_N", "Y5": "IOSEL_N", "Y6": "VRSEL_N", "Y7": "FNSEL_N"},
           note="region decoder (4 KiB slices of $0000-$7FFF)")
    d.gate("and", "RG0_N", "RG1_N", "RG01_N")
    d.gate("and", "RG2_N", "RG3_N", "RG23_N")
    d.gate("and", "RG01_N", "RG23_N", "RG03_N")
    d.gate("and", "RG03_N", "RG4_N", "ROMSEL_N")
    d.gate("or", "ROMSEL_N", "RD_N", "ROMOE_N")
    bank = bus("BK", 5)
    ra = ["RA12", "RA13", "RA14", "RA15", "RA16"]
    d.chip("74HC157", {"S": AB[14], "G": "GND", "1A": AB[12], "1B": bank[0], "1Y": ra[0],
                       "2A": AB[13], "2B": bank[1], "2Y": ra[1], "3A": "GND", "3B": bank[2],
                       "3Y": ra[2], "4A": "GND", "4B": bank[3], "4Y": ra[3]}, note="ROM bank mux")
    d.chip("74HC157", {"S": AB[14], "G": "GND", "1A": "GND", "1B": bank[4], "1Y": ra[4],
                       "2A": "GND", "2B": "GND", "3A": "GND", "3B": "GND", "4A": "GND", "4B": "GND"},
           note="ROM bank mux (bit 16)")
    rom_addr = AB[0:12] + ra + ["GND", "GND"]
    conn = {"A%d" % i: rom_addr[i] for i in range(19)}
    conn.update({"DQ%d" % i: DB[i] for i in range(8)})
    conn.update({"CE": "GND", "OE": "ROMOE_N", "WE": "VCC"})
    d.chip("SST39SF040", conn, ref=REF_ROM, note="boot firmware (SST39SF010A in a 040-wired socket)")
    d.gate("inv", AB[15], "A15_N")
    d.gate("inv", "WR_N", "WR")
    d.gate("and", "WR", "WIN", "WRP")                   # write pulse, dots 5.5-7.5
    d.gate("and", AB[13], AB[12], "A1312")
    d.gate("or", AB[14], "A1312", "A14OR")
    d.gate("and", AB[15], "A14OR", "PROT")              # $B000-$FFFF
    d.gate("and", "PROT", "FROMRAM", "BLOCK")
    d.gate("inv", "BLOCK", "BLOCK_N")
    d.gate("and", "WRP", "BLOCK_N", "WRP_OK")
    d.gate("nand", "WRP_OK", "WRP_OK", "RAMWE_N")
    conn = {"A%d" % i: AB[i] for i in range(15)}
    conn.update({"DQ%d" % i: DB[i] for i in range(8)})
    conn.update({"CE": "A15_N", "OE": "RD_N", "WE": "RAMWE_N"})
    d.chip("AS6C62256", conn, ref=REF_RAM, note="32 KiB SRAM at $8000")
    # FROM_RAM: A15 of the last instruction fetch
    d.gate("inv", "LD_IR_N", "LD_IR")
    d.chip("74HC157", {"S": "LD_IR", "G": "GND", "1A": "FROMRAM", "1B": AB[15], "1Y": "FR_D",
                       "2A": "GND", "2B": "GND", "3A": "GND", "3B": "GND", "4A": "GND", "4B": "GND"})

    # ================================================================ I/O
    d.sheet = "io"
    d.chip("74HC138", {"A": AB[0], "B": AB[1], "C": AB[2], "G2A": "IOSEL_N", "G2B": "RD_N",
                       "G1": "VCC", "Y0": "KBD_RD_N", "Y1": "KST_RD_N", "Y2": "SYS_RD_N",
                       "Y7": "IN_RD_N"}, note="I/O read enables (windowed)")
    d.chip("74HC138", {"A": AB[0], "B": AB[1], "C": AB[2], "G2A": "IOSEL_N", "G2B": "SRC_MEM_N",
                       "G1": "VCC", "Y0": "KBD_RAW_N", "Y2": "SYS_RAW_N"},
           note="I/O read side effects (sampled at the clock edge)")
    d.chip("74HC138", {"A": AB[0], "B": AB[1], "C": AB[2], "G2A": "IOSEL_N", "G2B": "WR_N",
                       "G1": "VCC", "Y2": "SYSW_N", "Y3": "BANKW_N", "Y4": "SXW_N",
                       "Y5": "SYW_N", "Y6": "OUTW_N"}, note="I/O write enables")
    reg377("BANKW_N", bank + ["NC_BK5", "NC_BK6", "NC_BK7"], "ROM bank register $5003")
    reg377("SXW_N", bus("SX", 7) + ["NC_SX7"], "SCROLL_X $5004")
    reg377("SYW_N", bus("SY", 5) + ["NC_SY5", "NC_SY6", "NC_SY7"], "SCROLL_Y $5005")
    # OUT bits 0 and 1 are the EEPROM's bit-banged SPI clock and data (docs/06)
    reg377("OUTW_N", ["EE_SCK", "EE_MOSI"] + bus("OUT", 8)[2:], "OUT_PORT $5006")
    d.gate("inv", "KBD_RAW_N", "KBD_RAW")
    d.gate("inv", "SYS_RAW_N", "SYS_RAW")
    d.gate("and", "TRAPF", "SYSW_N", "TRAP_K")
    d.gate("or", M[21], "TRAP_K", "TRAP_D")
    d.gate("and", "WR", "BLOCK", "VIOLEV")
    d.gate("and", "VIOLF", "SYSW_N", "VIOL_K")
    d.gate("or", "VIOLEV", "VIOL_K", "VIOL_D")
    d.chip("74HC74", {"1CLK": "CPUCLK", "1D": "KBD_RAW", "1CLR": "RST_N", "1PRE": "VCC",
                      "1Q": "KCLR",
                      "2CLK": "CPUCLK", "2D": "SYS_RAW", "2CLR": "RST_N", "2PRE": "VCC",
                      "2QN": "VCLR_N"}, note="read side effects: one-cycle pulses")
    d.chip("74HC74", {"1CLK": "CPUCLK", "1D": "TRAP_D", "1CLR": "RST_N", "1PRE": "VCC",
                      "1Q": "TRAPF",
                      "2CLK": "CPUCLK", "2D": "VIOL_D", "2CLR": "RST_N", "2PRE": "VCC",
                      "2Q": "VIOLF"}, note="TRAP and WRITE-VIOLATION latches")
    d.gate("and", "VBL", "VCLR_N", "VBL_K")
    d.gate("or", "VBLS", "VBL_K", "VBL_D")
    d.chip("74HC74", {"1CLK": "CHARCLK", "1D": "VBL_D", "1CLR": "VCC", "1PRE": "VCC", "1Q": "VBL",
                      "2CLK": "CPUCLK", "2D": "FR_D", "2CLR": "VCC", "2PRE": "VCC",
                      "2Q": "FROMRAM"}, note="VBLANK latch, FROM_RAM")
    drv541(["VBL", "TRAPF", "VIOLF", "GND", "GND", "GND", "GND", "GND"], "SYS_RD_N", "SYS_STATUS")
    drv541(["MISO"] + bus("EXIN", 7, 1), "IN_RD_N", "IN_PORT $5007")
    d.passive("RN", "10k", {1: "VCC", **{i + 2: n for i, n in enumerate(["MISO"] + bus("EXIN", 7, 1))}},
              ptype="rnet", note="IN_PORT pull-ups")
    for n in ["MISO"] + bus("EXIN", 7, 1):
        d.pullups[n] = "up"
    d.gate("or", "OUT2", "RST", "EE_CS_N")
    d.passive("U", "25LC512", {1: "EE_CS_N", 2: "MISO", 3: "VCC", 4: "GND", 5: "EE_MOSI",
                               6: "EE_SCK", 7: "VCC", 8: "VCC"}, ptype="eeprom", note="25LC512-I/P")
    d.passive("R", "1k", {1: "OUT3", 2: "SPK_B"})
    d.passive("Q", "2N3904", {1: "GND", 2: "SPK_B", 3: "SPK_C"}, ptype="npn")
    d.passive("BZ", "piezo", {1: "VCC", 2: "SPK_C"}, ptype="buzzer")

    # ================================================================ keyboard
    d.sheet = "keyboard"
    d.passive("J", "PS/2", {1: "KDATA", 2: "NC_K2", 3: "GND", 4: "KVCC", 5: "KCLK", 6: "NC_K6"},
              ptype="minidin6")
    d.passive("F", "200mA", {1: "VCC", 2: "KVCC"}, ptype="polyfuse")
    d.pull("KCLK", "up", "4.7k")
    d.pull("KDATA", "up", "4.7k")
    d.gate("schmitt", "KCLK", "KCLKI_N")               # rises on the falling PS/2 clock
    d.gate("schmitt", "KDATA", "KDATA_N")
    d.gate("schmitt", "KDATA_N", "KDATI")
    kp = bus("KP", 16)
    d.chip("74HC164", {"A": "KDATI", "B": "VCC", "CLK": "KCLKI_N", "CLR": "VCC",
                       "QA": kp[0], "QB": kp[1], "QC": kp[2], "QD": kp[3], "QE": kp[4],
                       "QF": kp[5], "QG": kp[6], "QH": kp[7]})
    d.chip("74HC164", {"A": kp[7], "B": "VCC", "CLK": "KCLKI_N", "CLR": "VCC",
                       "QA": kp[8], "QB": kp[9], "QC": kp[10]})
    d.chip("74HC161", {"CLK": "KCLKI_N", "CLR": "KCLR_N", "LOAD": "VCC", "ENP": "KREADY_N",
                       "ENT": "KREADY_N", "A": "GND", "B": "GND", "C": "GND", "D": "GND",
                       "QA": "KQ0", "QB": "KQ1", "QD": "KQ3"}, note="PS/2 bit counter")
    d.gate("and3", "KQ0", "KQ1", "KQ3", "KREADY")       # 11 bits received
    d.gate("inv", "KREADY", "KREADY_N")
    d.gate("inv_od", "KREADY", "KCLK")                  # hold the keyboard while a byte waits
    d.passive("D", "1N4148", {1: "KCLK", 2: "KTO_RC"}, ptype="diode", note="timeout RC discharge")
    d.passive("R", "47k", {1: "VCC", 2: "KTO_RC"})
    d.passive("C", "47n", {1: "KTO_RC", 2: "GND"})
    d.gate("schmitt", "KTO_RC", "KTO_N")
    d.gate("schmitt", "KTO_N", "KTO")                   # 2 ms without PS/2 clock
    d.gate("and", "KTO", "KREADY_N", "KTO_CLR")
    d.gate("or", "KCLR", "KTO_CLR", "KCLR_ANY")
    d.gate("nor", "KCLR_ANY", "RST", "KCLR_N")
    data_bits = [kp[9 - i] for i in range(8)]           # d0 = KP9 ... d7 = KP2
    drv541(data_bits, "KBD_RD_N", "KBD_DATA $5000")
    drv541(["KREADY", kp[1], kp[10], kp[0], "GND", "GND", "GND", "GND"], "KST_RD_N",
           "KBD_STATUS $5001")

    # ================================================================ video
    d.sheet = "video"
    d.gate("inv", "HRESET", "HRES_N")
    d.gate("inv", "VRESET", "VRES_N")
    h, v = bus("H", 7), bus("V", 10)
    d.chip("74HC163", {"CLK": "CHARCLK", "CLR": "HRES_N", "LOAD": "VCC", "ENP": "VCC",
                       "ENT": "VCC", "A": "GND", "B": "GND", "C": "GND", "D": "GND",
                       "QA": h[0], "QB": h[1], "QC": h[2], "QD": h[3], "RCO": "HC0"},
           note="H counter low")
    d.chip("74HC163", {"CLK": "CHARCLK", "CLR": "HRES_N", "LOAD": "VCC", "ENP": "VCC",
                       "ENT": "HC0", "A": "GND", "B": "GND", "C": "GND", "D": "GND",
                       "QA": h[4], "QB": h[5], "QC": h[6]}, note="H counter high")
    carry = "HRESET"
    for k in range(3):
        conn = {"CLK": "CHARCLK", "CLR": "VRES_N", "LOAD": "VCC", "ENP": "HRESET", "ENT": carry,
                "A": "GND", "B": "GND", "C": "GND", "D": "GND"}
        for i, q in enumerate(["QA", "QB", "QC", "QD"]):
            if 4 * k + i < 10:
                conn[q] = v[4 * k + i]
        if k < 2:
            conn["RCO"] = "VC%d" % k
            carry = "VC%d" % k
        d.chip("74HC163", conn, note="V counter")
    tr_addr = h + v + ["GND", "GND"]
    conn = {"A%d" % i: tr_addr[i] for i in range(19)}
    conn.update({"DQ%d" % i: "TR%d" % i for i in range(6)})
    conn.update({"CE": "GND", "OE": "GND", "WE": "VCC"})
    d.chip("SST39SF040", conn, note="VGA timing ROM (SST39SF010A)")
    d.chip("74AC574", {"CLK": "CHARCLK", "OE": "GND",
                       "D1": "TR0", "D2": "TR1", "D3": "TR2", "D4": "TR3", "D5": "TR4", "D6": "TR5",
                       "D7": "GND", "D8": "GND",
                       "Q1": "HSYNC_N", "Q2": "VSYNC_N", "Q3": "BLANK", "Q4": "HRESET",
                       "Q5": "VRESET", "Q6": "VBLS"}, note="timing register")
    col, row = bus("COL", 7), bus("ROW", 5)
    sx, sy = bus("SX", 7), bus("SY", 5)
    d.chip("74HC283", {"A1": h[0], "A2": h[1], "A3": h[2], "A4": h[3], "B1": sx[0], "B2": sx[1],
                       "B3": sx[2], "B4": sx[3], "C0": "GND", "S1": col[0], "S2": col[1],
                       "S3": col[2], "S4": col[3], "C4": "CC1"})
    d.chip("74HC283", {"A1": h[4], "A2": h[5], "A3": h[6], "A4": "GND", "B1": sx[4], "B2": sx[5],
                       "B3": sx[6], "B4": "GND", "C0": "CC1", "S1": col[4], "S2": col[5],
                       "S3": col[6]})
    d.chip("74HC283", {"A1": v[4], "A2": v[5], "A3": v[6], "A4": v[7], "B1": sy[0], "B2": sy[1],
                       "B3": sy[2], "B4": sy[3], "C0": "GND", "S1": row[0], "S2": row[1],
                       "S3": row[2], "S4": row[3], "C4": "RC1"})
    d.gate("xor", v[8], sy[4], "ROWX")
    d.gate("xor", "ROWX", "RC1", row[4])
    vid_addr = col + row
    vad = bus("VAD", 12)
    for k in range(3):
        conn = {"S": "PH2", "G": "GND"}
        for u in range(4):
            bit = 4 * k + u
            conn.update({"%dA" % (u + 1): vid_addr[bit], "%dB" % (u + 1): AB[bit],
                         "%dY" % (u + 1): vad[bit]})
        d.chip("74AC157", conn, note="VRAM address: video in phase 1, CPU in phase 2")
    d.gate("nand", "SRC_MEM_N", "WR_N", "MEMOP")
    d.gate("inv", "VRSEL_N", "VRSEL")
    d.gate("inv", "FNSEL_N", "FNSEL")
    d.gate("and3", "PH2", "VRSEL", "WR", "VROE_N")
    d.gate("nand", "WRP", "VRSEL", "VRWE_N")
    d.gate("and3", "WIN", "VRSEL", "MEMOP", "VBEN")
    d.gate("inv", "VBEN", "VBOE_N")
    vd = bus("VD", 8)
    conn = {"A%d" % i: vad[i] for i in range(12)}
    conn.update({"A12": "GND", "CE": "GND", "CE2": "VCC", "OE": "VROE_N",
                 "WE": "VRWE_N"})
    conn.update({"DQ%d" % i: vd[i] for i in range(8)})
    d.chip("AS6C6264", conn, ref=REF_VRAM, note="tile map")
    conn = {"DIR": "WR", "OE": "VBOE_N"}
    for i in range(8):
        conn["A%d" % (i + 1)] = DB[i]
        conn["B%d" % (i + 1)] = vd[i]
    d.chip("74AC245", conn, note="VRAM <-> CPU bus")
    ch = bus("CH", 8)
    conn = {"CLK": "DOT2", "OE": "GND"}
    for i in range(8):
        conn["D%d" % (i + 1)] = vd[i]
        conn["Q%d" % (i + 1)] = ch[i]
    d.chip("74HC574", conn, note="character latch (end of phase 1)")
    font_addr = v[0:4] + ch
    fad = bus("FAD", 12)
    for k in range(3):
        conn = {"S": "PH2", "G": "GND"}
        for u in range(4):
            bit = 4 * k + u
            conn.update({"%dA" % (u + 1): font_addr[bit], "%dB" % (u + 1): AB[bit],
                         "%dY" % (u + 1): fad[bit]})
        d.chip("74AC157", conn, note="font RAM address mux")
    d.gate("and3", "PH2", "FNSEL", "WR", "FNOE_N")
    d.gate("nand", "WRP", "FNSEL", "FNWE_N")
    d.gate("and3", "WIN", "FNSEL", "MEMOP", "FBEN")
    d.gate("inv", "FBEN", "FBOE_N")
    fd = bus("FD", 8)
    conn = {"A%d" % i: fad[i] for i in range(12)}
    conn.update({"A12": "GND", "CE": "GND", "CE2": "VCC", "OE": "FNOE_N",
                 "WE": "FNWE_N"})
    conn.update({"DQ%d" % i: fd[i] for i in range(8)})
    d.chip("AS6C6264", conn, ref=REF_FONT, note="font RAM")
    conn = {"DIR": "WR", "OE": "FBOE_N"}
    for i in range(8):
        conn["A%d" % (i + 1)] = DB[i]
        conn["B%d" % (i + 1)] = fd[i]
    d.chip("74AC245", conn, note="font RAM <-> CPU bus")
    fl = bus("FL", 8)
    conn = {"CLK": "DOT2", "OE": "GND"}
    for i in range(8):
        conn["D%d" % (i + 1)] = fd[i]
        conn["Q%d" % (i + 1)] = fl[i]
    d.chip("74HC574", conn, note="font latch 1 (end of phase 1)")
    px = bus("PX", 8)
    conn = {"CLK": "CHARCLK", "OE": "GND"}
    for i in range(8):
        conn["D%d" % (i + 1)] = fl[i]
        conn["Q%d" % (i + 1)] = px[i]
    d.chip("74AC574", conn, note="font latch 2 (character boundary)")
    conn = {"A": "DOT0", "B": "DOT1", "C": "DOT2", "G": "GND", "Y": "PIXR"}
    for i in range(8):
        conn["D%d" % i] = px[7 - i]                     # dot 0 shows bit 7
    d.chip("74AC151", conn, note="pixel select (replaces the obsolete 74AC299)")
    d.chip("74AC574", {"CLK": "DOTCLK", "OE": "GND", "D1": "PIXR", "D2": "BLANK",
                       "D3": "HSYNC_N", "D4": "VSYNC_N", "D5": "GND", "D6": "GND", "D7": "GND",
                       "D8": "GND", "Q1": "PIXQ", "Q2": "BLANKQ", "Q3": "HSQ", "Q4": "VSQ"},
           note="dot-clock output register")
    d.gate("ac_inv", "BLANKQ", "UNBLANK")
    d.gate("ac_and", "PIXQ", "UNBLANK", "VIDEO")
    for c in "RGB":
        d.passive("JP", "COL_" + c, {1: "COLEN_" + c, 2: "VCC"}, ptype="jumper")
        d.pull("COLEN_" + c, "down")
        d.gate("ac_and", "VIDEO", "COLEN_" + c, "V" + c)
        d.passive("R", "470", {1: "V" + c, 2: "VGA_" + c})
    d.passive("R", "100", {1: "HSQ", 2: "VGA_HS"})
    d.passive("R", "100", {1: "VSQ", 2: "VGA_VS"})
    d.passive("J", "VGA", {1: "VGA_R", 2: "VGA_G", 3: "VGA_B", 4: "NC_V4", 5: "GND", 6: "GND",
                           7: "GND", 8: "GND", 9: "NC_V9", 10: "GND", 11: "NC_V11", 12: "NC_V12",
                           13: "VGA_HS", 14: "VGA_VS", 15: "NC_V15", "SH": "GND"}, ptype="de15")

    # ================================================================ power & debug
    d.sheet = "power"
    d.passive("J", "USB-C power", {"A9": "VBUS", "B9": "VBUS", "A12": "GND", "B12": "GND",
                                    "A5": "USB_CC1", "B5": "USB_CC2", "SH": "GND"}, ptype="usbc_power")
    d.passive("R", "5.1k", {1: "USB_CC1", 2: "GND"})
    d.passive("R", "5.1k", {1: "USB_CC2", 2: "GND"})
    d.passive("F", "2A", {1: "VBUS", 2: "VCC"}, ptype="polyfuse")
    d.passive("D", "SMBJ5.0A", {1: "VCC", 2: "GND"}, ptype="tvs")
    d.passive("C", "470u", {1: "VCC", 2: "GND"}, ptype="electrolytic")
    d.passive("D", "PWR", {1: "GND", 2: "PWR_LED"}, ptype="led")       # 1 = K, 2 = A
    d.passive("R", "1k", {1: "VCC", 2: "PWR_LED"})
    d.passive("D", "HALT", {1: "GND", 2: "HALT_LED"}, ptype="led")
    d.passive("R", "1k", {1: "HALTED", 2: "HALT_LED"})
    d.finalize()
    logic_refs = [p.ref for p in d.parts.values() if p.kind == "logic"]
    for ref in logic_refs:
        d.passive("C", "100n", {1: "VCC", 2: "GND"}, note="decoupling for %s" % ref)
    d.sheet = "debug"
    la = AB + DB + ["CPUCLK", "RST_N", "STEP0", "STEP1", "STEP2", "STEP3", "WR_N", "RD_N",
                    "ROMSEL_N", "HSQ", "VSQ", "KCLK", "KDATA", "CHARCLK", "VCC", "GND"]
    d.passive("J", "LOGIC", {i + 1: la[i] for i in range(40)}, ptype="header2x20")
    exp = DB + AB[0:8] + ["IOSEL_N", "RD_N", "WR_N", "CPUCLK", "RST_N"] + bus("OUT", 4, 4) \
        + bus("EXIN", 7, 1) + ["VCC", "VCC", "GND", "GND", "GND"]
    d.passive("J", "EXPANSION", {i + 1: exp[i] for i in range(len(exp))}, ptype="header2x20")
    return d


if __name__ == "__main__":
    d = build()
    logic = [p for p in d.parts.values() if p.kind == "logic"]
    by = {}
    for p in logic:
        by[p.ptype] = by.get(p.ptype, 0) + 1
    print("%d logic packages, %d other parts, %d nets" %
          (len(logic), len(d.parts) - len(logic), len(d.nets())))
    for t, n in sorted(by.items()):
        print("  %-11s %d" % (t, n))
