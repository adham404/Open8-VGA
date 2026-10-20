"""Open8-VGA hardware parts library: pinouts and functional models.

Every part type has
  pins:    {pin name: pin number}  (DIP numbering, from the manufacturers' datasheets)
  power:   (VCC pin, GND pin) or None
  model:   a class with eval(get) -> {pin: 0/1/None}; clocked parts also have
           clock_pins and tick(pin, get) -> next state, applied by the simulator.
The simulator (gatesim.py) calls these with `get(pin_name)` returning 0, 1 or None (Z).
Author: Adham Elshafei
"""

Z = None


def b(v):
    return 1 if v else 0


class Part:
    """Base for combinational parts."""
    clock_pins = ()
    open_drain = ()

    def __init__(self, ref, ptype, params=None):
        self.ref, self.ptype, self.params = ref, ptype, params or {}
        self.state = {}

    def eval(self, g):
        return {}


# ------------------------------------------------------------------ pinouts
def quad2(names=("A", "B", "Y")):
    """74xx00/08/32/86 layout: gate n = (A, B, Y)."""
    a, bb, y = names
    return {"1" + a: 1, "1" + bb: 2, "1" + y: 3, "2" + a: 4, "2" + bb: 5, "2" + y: 6,
            "3" + y: 8, "3" + a: 9, "3" + bb: 10, "4" + y: 11, "4" + a: 12, "4" + bb: 13}


HEX_INV = {"1A": 1, "1Y": 2, "2A": 3, "2Y": 4, "3A": 5, "3Y": 6, "4Y": 8, "4A": 9,
           "5Y": 10, "5A": 11, "6Y": 12, "6A": 13}
NOR_02 = {"1Y": 1, "1A": 2, "1B": 3, "2Y": 4, "2A": 5, "2B": 6, "3A": 8, "3B": 9, "3Y": 10,
          "4A": 11, "4B": 12, "4Y": 13}
AND3_11 = {"1A": 1, "1B": 2, "2A": 3, "2B": 4, "2C": 5, "2Y": 6, "3Y": 8, "3A": 9, "3B": 10,
           "3C": 11, "1Y": 12, "1C": 13}
FF_74 = {"1CLR": 1, "1D": 2, "1CLK": 3, "1PRE": 4, "1Q": 5, "1QN": 6, "2QN": 8, "2Q": 9,
         "2PRE": 10, "2CLK": 11, "2D": 12, "2CLR": 13}
DEC_138 = {"A": 1, "B": 2, "C": 3, "G2A": 4, "G2B": 5, "G1": 6, "Y7": 7, "Y6": 9, "Y5": 10,
           "Y4": 11, "Y3": 12, "Y2": 13, "Y1": 14, "Y0": 15}
DEC_139 = {"1G": 1, "1A": 2, "1B": 3, "1Y0": 4, "1Y1": 5, "1Y2": 6, "1Y3": 7, "2Y3": 9,
           "2Y2": 10, "2Y1": 11, "2Y0": 12, "2B": 13, "2A": 14, "2G": 15}
MUX_151 = {"D3": 1, "D2": 2, "D1": 3, "D0": 4, "Y": 5, "W": 6, "G": 7, "C": 9, "B": 10,
           "A": 11, "D7": 12, "D6": 13, "D5": 14, "D4": 15}
MUX_153 = {"1G": 1, "B": 2, "1C3": 3, "1C2": 4, "1C1": 5, "1C0": 6, "1Y": 7, "2Y": 9,
           "2C0": 10, "2C1": 11, "2C2": 12, "2C3": 13, "A": 14, "2G": 15}
DEC_154 = dict({"Y%d" % i: i + 1 for i in range(11)},
               **{"Y11": 13, "Y12": 14, "Y13": 15, "Y14": 16, "Y15": 17, "G1": 18, "G2": 19,
                  "D": 20, "C": 21, "B": 22, "A": 23})
MUX_157 = {"S": 1, "1A": 2, "1B": 3, "1Y": 4, "2A": 5, "2B": 6, "2Y": 7, "3Y": 9, "3B": 10,
           "3A": 11, "4Y": 12, "4B": 13, "4A": 14, "G": 15}
CNT_161 = {"CLR": 1, "CLK": 2, "A": 3, "B": 4, "C": 5, "D": 6, "ENP": 7, "LOAD": 9,
           "ENT": 10, "QD": 11, "QC": 12, "QB": 13, "QA": 14, "RCO": 15}
SR_164 = {"A": 1, "B": 2, "QA": 3, "QB": 4, "QC": 5, "QD": 6, "CLK": 8, "CLR": 9, "QE": 10,
          "QF": 11, "QG": 12, "QH": 13}
XCV_245 = dict({"DIR": 1, "OE": 19}, **{"A%d" % i: i + 1 for i in range(1, 9)},
               **{"B%d" % i: 19 - i for i in range(1, 9)})
ADD_283 = {"S2": 1, "B2": 2, "A2": 3, "S1": 4, "A1": 5, "B1": 6, "C0": 7, "C4": 9, "S4": 10,
           "B4": 11, "A4": 12, "S3": 13, "A3": 14, "B3": 15}
REG_377 = {"E": 1, "Q1": 2, "D1": 3, "D2": 4, "Q2": 5, "Q3": 6, "D3": 7, "D4": 8, "Q4": 9,
           "CP": 11, "Q5": 12, "D5": 13, "D6": 14, "Q6": 15, "Q7": 16, "D7": 17, "D8": 18,
           "Q8": 19}
BUF_541 = dict({"OE1": 1, "OE2": 19}, **{"A%d" % i: i + 1 for i in range(1, 9)},
               **{"Y%d" % i: 19 - i for i in range(1, 9)})
REG_574 = dict({"OE": 1, "CLK": 11}, **{"D%d" % i: i + 1 for i in range(1, 9)},
               **{"Q%d" % i: 20 - i for i in range(1, 9)})
FLASH_32 = {"A18": 1, "A16": 2, "A15": 3, "A12": 4, "A7": 5, "A6": 6, "A5": 7, "A4": 8,
            "A3": 9, "A2": 10, "A1": 11, "A0": 12, "DQ0": 13, "DQ1": 14, "DQ2": 15, "DQ3": 17,
            "DQ4": 18, "DQ5": 19, "DQ6": 20, "DQ7": 21, "CE": 22, "A10": 23, "OE": 24, "A11": 25,
            "A9": 26, "A8": 27, "A13": 28, "A14": 29, "A17": 30, "WE": 31}
SRAM_28 = {"A14": 1, "A12": 2, "A7": 3, "A6": 4, "A5": 5, "A4": 6, "A3": 7, "A2": 8, "A1": 9,
           "A0": 10, "DQ0": 11, "DQ1": 12, "DQ2": 13, "DQ3": 15, "DQ4": 16, "DQ5": 17,
           "DQ6": 18, "DQ7": 19, "CE": 20, "A10": 21, "OE": 22, "A11": 23, "A9": 24, "A8": 25,
           "A13": 26, "WE": 27}
SRAM8K_28 = dict(SRAM_28)
del SRAM8K_28["A14"], SRAM8K_28["A13"]
SRAM8K_28.update({"NC1": 1, "CE2": 26})
EE_8 = {"CS": 1, "SO": 2, "WP": 3, "SI": 5, "SCK": 6, "HOLD": 7}
T555 = {"TRIG": 2, "OUT": 3, "RESET": 4, "CTRL": 5, "THR": 6, "DIS": 7}


# ------------------------------------------------------------------ models
class Gates(Part):
    """Quad/hex gate packages. kind: nand nor and or xor inv inv_od schmitt and3."""

    def eval(self, g):
        k = self.params["kind"]
        out = {}
        if k in ("inv", "inv_od", "schmitt"):
            for n in range(1, 7):
                a = g("%dA" % n)
                if a is None:
                    continue
                v = 1 - a
                out["%dY" % n] = (Z if v else 0) if k == "inv_od" else v
            return out
        if k == "and3":
            for n in range(1, 4):
                vals = [g("%d%s" % (n, x)) for x in "ABC"]
                if None not in vals:
                    out["%dY" % n] = b(all(vals))
            return out
        for n in range(1, 5):
            a, c = g("%dA" % n), g("%dB" % n)
            if a is None or c is None:
                continue
            out["%dY" % n] = {"nand": 1 - (a & c), "nor": 1 - (a | c), "and": a & c,
                              "or": a | c, "xor": a ^ c}[k]
        return out

    @property
    def open_drain(self):
        return tuple("%dY" % n for n in range(1, 7)) if self.params["kind"] == "inv_od" else ()


class DFF74(Part):
    clock_pins = ("1CLK", "2CLK")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.state = {"1": 0, "2": 0}

    def eval(self, g):
        out = {}
        for n in "12":
            q = self.state[n]
            clr, pre = g(n + "CLR"), g(n + "PRE")
            if clr == 0 and pre == 0:
                out[n + "Q"], out[n + "QN"] = 1, 1
                continue
            if clr == 0:
                q = 0
            elif pre == 0:
                q = 1
            self.state[n] = q
            out[n + "Q"], out[n + "QN"] = q, 1 - q
        return out

    def tick(self, pin, g):
        n = pin[0]
        if g(n + "CLR") == 0 or g(n + "PRE") == 0:
            return
        d = g(n + "D")
        self.state[n] = 0 if d is None else d


class Dec138(Part):
    def eval(self, g):
        en = g("G1") == 1 and g("G2A") == 0 and g("G2B") == 0
        sel = (g("A") or 0) | ((g("B") or 0) << 1) | ((g("C") or 0) << 2)
        return {"Y%d" % i: 0 if (en and i == sel) else 1 for i in range(8)}


class Dec139(Part):
    def eval(self, g):
        out = {}
        for n in "12":
            en = g(n + "G") == 0
            sel = (g(n + "A") or 0) | ((g(n + "B") or 0) << 1)
            for i in range(4):
                out["%sY%d" % (n, i)] = 0 if (en and i == sel) else 1
        return out


class Dec154(Part):
    def eval(self, g):
        en = g("G1") == 0 and g("G2") == 0
        sel = sum((g(x) or 0) << i for i, x in enumerate("ABCD"))
        return {"Y%d" % i: 0 if (en and i == sel) else 1 for i in range(16)}


class Mux151(Part):
    def eval(self, g):
        if g("G") == 1:
            return {"Y": 0, "W": 1}
        sel = (g("A") or 0) | ((g("B") or 0) << 1) | ((g("C") or 0) << 2)
        v = g("D%d" % sel) or 0
        return {"Y": v, "W": 1 - v}


class Mux153(Part):
    def eval(self, g):
        sel = (g("A") or 0) | ((g("B") or 0) << 1)
        out = {}
        for n in "12":
            out[n + "Y"] = 0 if g(n + "G") == 1 else (g("%sC%d" % (n, sel)) or 0)
        return out


class Mux157(Part):
    def eval(self, g):
        s = g("S")
        out = {}
        for n in "1234":
            out[n + "Y"] = 0 if g("G") == 1 else (g(n + ("B" if s else "A")) or 0)
        return out


class Counter161(Part):
    """74HC161 (async clear) / 74HC163 (sync clear): params sync_clear."""
    clock_pins = ("CLK",)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.state = {"q": 0}

    def eval(self, g):
        if not self.params.get("sync_clear") and g("CLR") == 0:
            self.state["q"] = 0
        q = self.state["q"]
        out = {"QA": q & 1, "QB": (q >> 1) & 1, "QC": (q >> 2) & 1, "QD": (q >> 3) & 1}
        out["RCO"] = b(q == 15 and g("ENT") == 1)
        return out

    def tick(self, pin, g):
        q = self.state["q"]
        if g("CLR") == 0:
            q = 0
        elif g("LOAD") == 0:
            q = sum((g(x) or 0) << i for i, x in enumerate("ABCD"))
        elif g("ENP") == 1 and g("ENT") == 1:
            q = (q + 1) & 15
        self.state["q"] = q


class Shift164(Part):
    clock_pins = ("CLK",)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.state = {"q": 0}

    def eval(self, g):
        if g("CLR") == 0:
            self.state["q"] = 0
        q = self.state["q"]
        return {n: (q >> i) & 1 for i, n in enumerate(["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH"])}

    def tick(self, pin, g):
        if g("CLR") == 0:
            return
        bit = (g("A") or 0) & (g("B") or 0)
        self.state["q"] = ((self.state["q"] << 1) | bit) & 0xFF


class Xcvr245(Part):
    def eval(self, g):
        if g("OE") != 0:
            return {("A%d" % i): Z for i in range(1, 9)} | {("B%d" % i): Z for i in range(1, 9)}
        if g("DIR") == 1:                   # A -> B
            out = {"B%d" % i: g("A%d" % i) for i in range(1, 9)}
            out.update({"A%d" % i: Z for i in range(1, 9)})
        else:
            out = {"A%d" % i: g("B%d" % i) for i in range(1, 9)}
            out.update({"B%d" % i: Z for i in range(1, 9)})
        return out


class Adder283(Part):
    def eval(self, g):
        a = sum((g("A%d" % i) or 0) << (i - 1) for i in range(1, 5))
        c = sum((g("B%d" % i) or 0) << (i - 1) for i in range(1, 5))
        s = a + c + (g("C0") or 0)
        out = {"S%d" % i: (s >> (i - 1)) & 1 for i in range(1, 5)}
        out["C4"] = (s >> 4) & 1
        return out


class Reg377(Part):
    clock_pins = ("CP",)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.state = {"q": 0}

    def eval(self, g):
        return {"Q%d" % i: (self.state["q"] >> (i - 1)) & 1 for i in range(1, 9)}

    def tick(self, pin, g):
        if g("E") == 0:
            self.state["q"] = sum((g("D%d" % i) or 0) << (i - 1) for i in range(1, 9))


class Buf541(Part):
    def eval(self, g):
        en = g("OE1") == 0 and g("OE2") == 0
        return {"Y%d" % i: (g("A%d" % i) if en else Z) for i in range(1, 9)}


class Reg574(Part):
    clock_pins = ("CLK",)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.state = {"q": 0}

    def eval(self, g):
        en = g("OE") == 0
        return {"Q%d" % i: ((self.state["q"] >> (i - 1)) & 1 if en else Z) for i in range(1, 9)}

    def tick(self, pin, g):
        self.state["q"] = sum((g("D%d" % i) or 0) << (i - 1) for i in range(1, 9))


class Memory(Part):
    """Flash or SRAM. params: size, data (bytearray), abits (list of pin names in bit order),
    writable, chip-enable pins. Writes happen while WE is low (level, end value kept)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mem = self.params["data"]

    def addr(self, g):
        return sum((g(p) or 0) << i for i, p in enumerate(self.params["abits"]))

    def selected(self, g):
        if self.params.get("ce2") and g("CE2") != 1:
            return False
        return g("CE") == 0

    def eval(self, g):
        dq = ["DQ%d" % i for i in range(8)]
        if not self.selected(g):
            return {p: Z for p in dq}
        a = self.addr(g) % len(self.mem)
        if self.params.get("writable") and g("WE") == 0:
            v = sum((g(p) or 0) << i for i, p in enumerate(dq))
            self.mem[a] = v
            self.writes = getattr(self, "writes", 0) + 1
            return {p: Z for p in dq}
        if g("OE") == 0:
            v = self.mem[a]
            return {p: (v >> i) & 1 for i, p in enumerate(dq)}
        return {p: Z for p in dq}


class Passive(Part):
    """Resistors, capacitors, LEDs, connectors, oscillators: no logic in the netlist sim
    (stimuli such as the oscillator, 555, buttons and the PS/2 connector are driven by the
    testbench)."""


TYPES = {
    # name: (pins, vcc, gnd, model, params, package pins)
    "74HC00": (quad2(), 14, 7, Gates, {"kind": "nand"}, 14),
    "74HC02": (NOR_02, 14, 7, Gates, {"kind": "nor"}, 14),
    "74HC04": (HEX_INV, 14, 7, Gates, {"kind": "inv"}, 14),
    "74AC04": (HEX_INV, 14, 7, Gates, {"kind": "inv"}, 14),
    "74HC05": (HEX_INV, 14, 7, Gates, {"kind": "inv_od"}, 14),
    "74HC08": (quad2(), 14, 7, Gates, {"kind": "and"}, 14),
    "74AC08": (quad2(), 14, 7, Gates, {"kind": "and"}, 14),
    "74HC11": (AND3_11, 14, 7, Gates, {"kind": "and3"}, 14),
    "74HC14": (HEX_INV, 14, 7, Gates, {"kind": "schmitt"}, 14),
    "74HC32": (quad2(), 14, 7, Gates, {"kind": "or"}, 14),
    "74HC86": (quad2(), 14, 7, Gates, {"kind": "xor"}, 14),
    "74HC74": (FF_74, 14, 7, DFF74, {}, 14),
    "74AC74": (FF_74, 14, 7, DFF74, {}, 14),
    "74HC138": (DEC_138, 16, 8, Dec138, {}, 16),
    "74AC138": (DEC_138, 16, 8, Dec138, {}, 16),
    "74HC139": (DEC_139, 16, 8, Dec139, {}, 16),
    "74AC151": (MUX_151, 16, 8, Mux151, {}, 16),
    "74HC153": (MUX_153, 16, 8, Mux153, {}, 16),
    "74HC154": (DEC_154, 24, 12, Dec154, {}, 24),
    "74HC157": (MUX_157, 16, 8, Mux157, {}, 16),
    "74AC157": (MUX_157, 16, 8, Mux157, {}, 16),
    "74HC161": (CNT_161, 16, 8, Counter161, {"sync_clear": False}, 16),
    "74AC161": (CNT_161, 16, 8, Counter161, {"sync_clear": False}, 16),
    "74HC163": (CNT_161, 16, 8, Counter161, {"sync_clear": True}, 16),
    "74HC164": (SR_164, 14, 7, Shift164, {}, 14),
    "74HC245": (XCV_245, 20, 10, Xcvr245, {}, 20),
    "74AC245": (XCV_245, 20, 10, Xcvr245, {}, 20),
    "74HC283": (ADD_283, 16, 8, Adder283, {}, 16),
    "74HC377": (REG_377, 20, 10, Reg377, {}, 20),
    "74HC541": (BUF_541, 20, 10, Buf541, {}, 20),
    "74HC574": (REG_574, 20, 10, Reg574, {}, 20),
    "74AC574": (REG_574, 20, 10, Reg574, {}, 20),
    "SST39SF040": (FLASH_32, 32, 16, Memory, {}, 32),
    "AS6C62256": (SRAM_28, 28, 14, Memory, {"writable": True}, 28),
    "AS6C6264": (SRAM8K_28, 28, 14, Memory, {"writable": True, "ce2": True}, 28),
    "25LC512": (EE_8, 8, 4, Passive, {}, 8),
    "NE555": (T555, 8, 1, Passive, {}, 8),
}

FLASH_ABITS = ["A%d" % i for i in range(19)]
SRAM_ABITS = ["A%d" % i for i in range(15)]
SRAM8K_ABITS = ["A%d" % i for i in range(13)]


def check_tables():
    """Every pin number used once, within the package, and not on a power pin."""
    problems = []
    for name, (pins, vcc, gnd, _, _, npins) in TYPES.items():
        nums = list(pins.values())
        if len(set(nums)) != len(nums):
            problems.append("%s: duplicate pin numbers" % name)
        if vcc in nums or gnd in nums:
            problems.append("%s: logic pin on a power pin" % name)
        if any(not 1 <= n <= npins for n in nums):
            problems.append("%s: pin outside 1-%d" % (name, npins))
    return problems
