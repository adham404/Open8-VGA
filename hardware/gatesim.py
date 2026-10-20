"""Gate-level (chip-pin level) simulation of the Open8-VGA netlist.

Each chip is modelled at its pins (lib.py), nets carry 0/1/Z, tri-state buses are resolved
and contention is recorded. Time advances in half dot-clock steps; inside a step, changes
propagate in delta waves, and every flip-flop clocked by a net that rose in a wave samples
its inputs before any of them updates (like real edge-triggered logic with zero hold).
The testbench drives the oscillator, buttons, PS/2 lines and the reset supervisor.
Author: Adham Elshafei
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lib      # noqa: E402
import design   # noqa: E402

TRISTATE = {"74HC245", "74AC245", "74HC541", "74HC574", "74AC574", "SST39SF040",
            "AS6C62256", "AS6C6264"}


def output_pins(ptype):
    """Pins a part type can drive (found by evaluating its model once)."""
    pins, _, _, model, params, _ = lib.TYPES[ptype]
    m = model("x", ptype, dict(params, data=bytearray(1 << 19), abits=lib.FLASH_ABITS))
    outs = set(m.eval(lambda p: 0).keys()) | set(m.eval(lambda p: 1).keys())
    if ptype in ("74HC245", "74AC245"):
        outs = {p for p in pins if p[0] in "AB" and p[1:].isdigit()}
    if ptype in ("SST39SF040", "AS6C62256", "AS6C6264"):
        outs = {p for p in pins if p.startswith("DQ")}
    return outs


def check(d):
    """Static netlist checks. Returns a list of problems (empty = clean)."""
    problems = []
    nets = d.nets()
    drivers, readers = {}, {}
    external = set(EXTERNAL)
    for p in d.parts.values():
        if p.kind != "logic":
            continue
        pins = lib.TYPES[p.ptype][0]
        outs = output_pins(p.ptype)
        for name in pins:
            if name not in p.conn and name not in outs and not name.startswith("NC"):
                problems.append("%s (%s) input %s not connected" % (p.ref, p.ptype, name))
        for name, net in p.conn.items():
            if name in outs:
                drivers.setdefault(net, []).append((p.ref, name, p.ptype))
                if p.ptype in ("74HC245", "74AC245", "SST39SF040", "AS6C62256", "AS6C6264"):
                    readers.setdefault(net, []).append((p.ref, name))
            else:
                readers.setdefault(net, []).append((p.ref, name))
    for net, rd in readers.items():
        if net in ("VCC", "GND") or net in drivers or net in external or net in d.pullups:
            continue
        problems.append("net %s is read by %s but nothing drives it" % (net, rd[:3]))
    for net, dr in drivers.items():
        if net in ("VCC", "GND"):
            problems.append("output %s.%s drives a power net" % (dr[0][0], dr[0][1]))
            continue
        if len(dr) > 1:
            push_pull = [x for x in dr if x[2] not in TRISTATE and x[2] != "74HC05"]
            if push_pull:
                problems.append("net %s has %d drivers incl. push-pull %s" % (net, len(dr), push_pull[0][:2]))
    # the power-entry sheet shares only the supply rails with the logic: anything else
    # crossing over is a net-name collision (two signals given the same name)
    for net, pins in nets.items():
        if net in ("VCC", "GND", "HALTED"):       # HALTED lights the HALT LED by the power LED
            continue
        sheets = {d.parts[ref].sheet for ref, _, _ in pins}
        if "power" in sheets and len(sheets) > 1:
            problems.append("net %s joins the power sheet to %s (name collision?)"
                            % (net, sorted(sheets - {"power"})))
    for net, pins in nets.items():
        if len(pins) == 1 and not net.startswith("NC") and net not in ("VCC", "GND") \
                and net not in external:
            ref, num, name = pins[0]
            part = d.parts[ref]
            if part.kind == "logic" and name in output_pins(part.ptype):
                continue                                # unused output: fine
            problems.append("net %s has only one connection (%s pin %s)" % (net, ref, num))
    return problems


# nets driven by the testbench (oscillator, switches, buttons, keyboard, supervisor, RC timers)
EXTERNAL = {"DOTCLK": 0, "STEP_MODE": 0, "SLOW_SEL": 0, "SLOWCLK": 0, "RSTRAW_N": None,
            "STEPBTN_RC": 1, "CONTBTN_RC": 1, "KCLK": None, "KDATA": None, "KTO_RC": 0,
            "MISO": None}


class Board:
    def __init__(self, roms, d=None):
        """roms: {"ucode": [3 x bytes], "alu": [r0, r1, f0, f1], "firmware": bytes,
        "timing": bytes}"""
        self.d = d or design.build()
        self.nets = {}
        self.drv = {}           # net -> {(ref, pin): value}
        self.readers = {}       # net -> set(ref)
        self.clocks = {}        # net -> [(ref, pin)]
        self.chips = {}
        self.pins = {}          # ref -> {pin: net}
        self.contention = []
        flash_queue = list(roms["ucode"]) + list(roms["alu"])
        for p in self.d.parts.values():
            if p.kind != "logic":
                continue
            _, _, _, model, params, _ = lib.TYPES[p.ptype]
            params = dict(params)
            if p.ptype == "SST39SF040":
                if p.ref == design.REF_ROM:
                    data = roms["firmware"]
                elif "timing" in p.note:
                    data = roms["timing"]
                else:
                    data = flash_queue.pop(0)
                params.update(data=bytearray(data), abits=lib.FLASH_ABITS)
            elif p.ptype == "AS6C62256":
                params.update(data=bytearray(0x8000), abits=lib.SRAM_ABITS)
            elif p.ptype == "AS6C6264":
                params.update(data=bytearray(0x2000), abits=lib.SRAM8K_ABITS)
            chip = model(p.ref, p.ptype, params)
            self.chips[p.ref] = chip
            self.pins[p.ref] = dict(p.conn)
            for name, net in p.conn.items():
                self.readers.setdefault(net, set()).add(p.ref)
                if name in chip.clock_pins:
                    self.clocks.setdefault(net, []).append((p.ref, name))
        assert not flash_queue, "ROM images left over"
        for net in set(n for pins in self.pins.values() for n in pins.values()):
            self.nets[net] = 0
        self.nets["VCC"], self.nets["GND"] = 1, 0
        self.ext = dict(EXTERNAL)
        # buses with tri-state drivers hold their last value between drive windows
        # (10 k pull-up x ~100 pF = ~1 us, far longer than any hold time)
        self.keepers = set()
        for p in self.d.parts.values():
            if p.kind == "logic" and p.ptype in TRISTATE:
                outs = output_pins(p.ptype)
                self.keepers |= {net for name, net in p.conn.items() if name in outs}
        self.prev_clock = {}
        # start every pulled or externally driven net at its resting level (no false
        # clock edges at power-up)
        for net, direction in self.d.pullups.items():
            if net in self.nets and net not in self.keepers:
                self.nets[net] = 1 if direction == "up" else 0
        for net, val in self.ext.items():
            if val is not None and net in self.nets:
                self.nets[net] = val
        self.queue = set(self.chips)
        self.settle()
        self.contention = []        # the power-up instant (nothing settled yet) does not count

    # ---------------------------------------------------------------- core
    def get(self, ref):
        pins, nets = self.pins[ref], self.nets
        return lambda name: nets.get(pins[name]) if name in pins else None

    def resolve(self, net):
        vals = [v for v in self.drv.get(net, {}).values() if v is not None]
        if net in self.ext and self.ext[net] is not None:
            vals.append(self.ext[net])
        if vals:
            v = vals[0]
            if any(x != v for x in vals):
                v = 0 if net in ("KCLK", "KDATA") else v       # open-drain wired-AND
                if net not in ("KCLK", "KDATA"):
                    self.contention.append((self.time, net, dict(self.drv.get(net, {}))))
            return v
        pull = self.d.pullups.get(net)
        if pull and net not in self.keepers:
            return 1 if pull == "up" else 0
        return self.nets.get(net, 0)            # floating bus: keeps its charge

    def settle(self, max_waves=200):
        waves = 0
        while self.queue:
            waves += 1
            if waves > max_waves:
                raise RuntimeError("logic did not settle (oscillation?) at t=%s" % self.time)
            current, self.queue = self.queue, set()
            changed = set()
            for ref in current:
                outs = self.chips[ref].eval(self.get(ref))
                pins = self.pins[ref]
                for pin, val in outs.items():
                    net = pins.get(pin)
                    if net is None or net in ("VCC", "GND"):
                        continue
                    dmap = self.drv.setdefault(net, {})
                    if dmap.get((ref, pin), "x") != val:
                        dmap[(ref, pin)] = val
                        changed.add(net)
            rose = []
            for net in changed:
                old = self.nets.get(net)
                new = self.resolve(net)
                if new != old:
                    self.nets[net] = new
                    self.queue |= self.readers.get(net, set())
                    if old == 0 and new == 1 and net in self.clocks:
                        rose.append(net)
            if rose:
                ticks = [(ref, pin) for net in rose for ref, pin in self.clocks[net]]
                # every flip-flop on a rising clock samples before any of them changes
                snapshots = []
                for ref, pin in ticks:
                    chip = self.chips[ref]
                    before = {k: (dict(v) if isinstance(v, dict) else v) for k, v in chip.state.items()}
                    chip.tick(pin, self.get(ref))
                    snapshots.append((chip, before, dict(chip.state)))
                # (ticks read only nets, never other chips' state, so applying in order is safe)
                for ref, _ in ticks:
                    self.queue.add(ref)

    def set_ext(self, net, value):
        if self.ext.get(net) != value:
            self.ext[net] = value
            old = self.nets.get(net)
            new = self.resolve(net)
            if new != old:
                self.nets[net] = new
                self.queue |= self.readers.get(net, set())
                if old == 0 and new == 1 and net in self.clocks:
                    for ref, pin in self.clocks[net]:
                        self.chips[ref].tick(pin, self.get(ref))
                        self.queue.add(ref)
            self.settle()

    time = 0

    def half_dot(self):
        self.time += 1
        self.set_ext("DOTCLK", 1 - (self.ext["DOTCLK"] or 0))

    def run_dots(self, n):
        for _ in range(2 * n):
            self.half_dot()

    def run_cycles(self, n):
        self.run_dots(8 * n)

    # ---------------------------------------------------------------- inspection
    def chip_by_note(self, text):
        for p in self.d.parts.values():
            if text in p.note:
                return self.chips[p.ref]
        raise KeyError(text)

    def reg(self, note):
        return self.chip_by_note(note).state["q"]

    def counters(self, prefix):
        v = 0
        for k in range(4):
            v |= self.chip_by_note("%s bits %d-%d" % (prefix, 4 * k, 4 * k + 3)).state["q"] << (4 * k)
        return v

    def cpu_state(self):
        return {"a": self.reg("register A"), "b": self.reg("register B"),
                "x": self.counters("X"), "sp": self.reg("SP"), "pc": self.counters("PC"),
                "flags": self.reg("FLAGS") & 0xF,
                "step": self.chip_by_note("microstep counter").state["q"]}

    def memory(self, ref):
        return self.chips[ref].mem


def load_roms():
    root = os.path.join(HERE, "..", "build", "rom")
    rd = lambda n: open(os.path.join(root, n), "rb").read()
    return {"ucode": [rd("ucode%d.bin" % k) for k in range(3)],
            "alu": [rd(n) for n in ("alu_r0.bin", "alu_r1.bin", "alu_f0.bin", "alu_f1.bin")],
            "firmware": rd("firmware.bin"), "timing": rd("vga_timing.bin")}
