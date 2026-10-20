"""Grouped placement for the Open8-VGA board.

Parts go into a slot grid: wide rows (32/28/24-pin wide DIPs and the oscillator) at the top,
narrow rows (the 7.62 mm DIPs and the resistor networks) below, and a strip of cells on the
left for the small discretes, beside the edge connectors. Every 100 nF decoupling capacitor
sits just above the chip it serves. Simulated annealing swaps parts between slots of the same
kind to minimise the half-perimeter length of the signal nets (clock nets weighted 3x).

Input: build/fp_geom.json (dump_fp.py). Output: build/placement.json, read by apply.py.
Author: Adham Elshafei
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, ".."))

import design  # noqa: E402

MARGIN = 3.0
STRIP_X, CELL_W, CELL_H, BIG_H = 18.0, 13.0, 8.5, 16.0
CHIP_X = 46.0
CHIP_W = 264.0
NARROW_W, NARROW_H = 11.5, 31.5
WIDE_W, WIDE_H = 21.0, 48.0
CHIP_TOP = 4.0              # chip body starts this far below its row top; the cap sits above
WIDE_IN_ROW2 = 5
NARROW_ROWS = 5

FIXED = ("J1", "J2", "J3", "J4", "J5")
POWER = {"VCC", "GND"}
CLOCK = {"DOTCLK", "DOTCLK_N", "CHARCLK", "CPUCLK", "DOT0", "DOT1", "DOT2", "PH2", "WIN",
         "WIN_N", "WINRAW", "DOTX"}


def rot_box(box, rot):
    l, t, r, b = box
    pts = [rotate(x, y, rot) for x in (l, r) for y in (t, b)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def rotate(x, y, rot):
    """KiCad orientation (degrees, counter-clockwise on screen, y down)."""
    a = math.radians(rot)
    c, s = round(math.cos(a)), round(math.sin(a))
    return x * c + y * s, -x * s + y * c


def main():
    geom = json.load(open(os.path.join(ROOT, "build", "fp_geom.json")))
    d = design.build()
    decap_of = {}
    for p in d.parts.values():
        if p.note.startswith("decoupling for "):
            decap_of[p.ref] = p.note.split()[-1]
    caps_for = {}
    for cap, chip in decap_of.items():
        caps_for.setdefault(chip, []).append(cap)

    # ---- classify parts
    items = {}          # ref -> (kind, rot)
    for ref, g in geom.items():
        if ref in FIXED or ref in decap_of:
            continue
        fp = g["fp"].split(":")[1]
        if fp.startswith("DIP-") and "W15.24" in fp:
            items[ref] = ("wide", 0)
        elif fp.startswith("DIP-"):
            items[ref] = ("narrow", 0)
        elif fp.startswith("Oscillator"):
            items[ref] = ("wide", 90)
        elif fp.startswith("R_Array"):
            items[ref] = ("narrow", 90)
        else:
            l, t, r, b = g["box"]
            big = (r - l) > CELL_W - 0.3 or (b - t) > CELL_H - 0.3
            items[ref] = ("big" if big else "cell", 0)

    # ---- slots (top-left corner of the space each part may use)
    slots = {"wide": [], "narrow": [], "cell": [], "big": []}
    y = MARGIN
    for i in range(int(CHIP_W // WIDE_W)):
        slots["wide"].append((CHIP_X + i * WIDE_W, y))
    y += WIDE_H
    for i in range(WIDE_IN_ROW2):
        slots["wide"].append((CHIP_X + i * WIDE_W, y))
    x0 = CHIP_X + WIDE_IN_ROW2 * WIDE_W
    for i in range(int((CHIP_X + CHIP_W - x0) // NARROW_W)):
        slots["narrow"].append((x0 + i * NARROW_W, y))
    y += WIDE_H
    for r in range(NARROW_ROWS):
        for i in range(int(CHIP_W // NARROW_W)):
            slots["narrow"].append((CHIP_X + i * NARROW_W, y))
        y += NARROW_H
    board_h = y + MARGIN
    board_w = CHIP_X + CHIP_W + MARGIN
    yy = MARGIN
    for _ in range(2):
        for c in range(2):
            slots["big"].append((STRIP_X + c * CELL_W, yy))
        yy += BIG_H
    while yy + CELL_H <= board_h - MARGIN:
        for c in range(2):
            slots["cell"].append((STRIP_X + c * CELL_W, yy))
        yy += CELL_H

    for kind in slots:
        need = sum(1 for k in items.values() if k[0] == kind)
        print("%-6s %3d parts, %3d slots" % (kind, need, len(slots[kind])))
        assert need <= len(slots[kind]), kind

    # ---- pad offsets relative to the slot corner, per part
    def anchor_offset(ref, kind, rot):
        """Where the footprint origin goes relative to the slot's top-left corner."""
        l, t, r, b = rot_box(geom[ref]["box"], rot)
        top = CHIP_TOP if kind in ("wide", "narrow") else 0.2
        return 0.3 - l, top - t

    offs, pads = {}, {}
    for ref, (kind, rot) in items.items():
        ox, oy = anchor_offset(ref, kind, rot)
        offs[ref] = (ox, oy)
        pads[ref] = []
        for p in geom[ref]["pads"]:
            px, py = rotate(p["x"], p["y"], rot)
            pads[ref].append((p["net"], ox + px, oy + py))

    nets = {}           # net -> list of (ref or None for fixed, dx, dy)
    for ref, plist in pads.items():
        for net, px, py in plist:
            if net and net not in POWER and not net.startswith("unconnected"):
                nets.setdefault(net, []).append((ref, px, py))
    for ref in FIXED:
        g = geom[ref]
        x0f, y0f, rot = g["at"]
        for p in g["pads"]:
            if p["net"] and p["net"] not in POWER:
                px, py = rotate(p["x"], p["y"], rot)
                nets.setdefault(p["net"], []).append((None, x0f + px, y0f + py))
    nets = {n: v for n, v in nets.items() if len(v) > 1}
    weight = {n: (3.0 if n in CLOCK else 1.0) for n in nets}
    nets_of = {}
    for n, v in nets.items():
        for ref, _, _ in v:
            if ref:
                nets_of.setdefault(ref, set()).add(n)

    # ---- initial assignment: by sheet, in slot order (a sensible start)
    random.seed(8)
    pos = {}
    occupant = {kind: [None] * len(slots[kind]) for kind in slots}
    order = sorted(items, key=lambda r: (d.parts[r].sheet if r in d.parts else "", r))
    nxt = {kind: 0 for kind in slots}
    for ref in order:
        kind = items[ref][0]
        i = nxt[kind]
        nxt[kind] += 1
        pos[ref] = i
        occupant[kind][i] = ref

    def where(ref):
        sx, sy = slots[items[ref][0]][pos[ref]]
        return sx, sy

    def net_len(n):
        xs, ys = [], []
        for ref, px, py in nets[n]:
            if ref is None:
                xs.append(px)
                ys.append(py)
            else:
                sx, sy = where(ref)
                xs.append(sx + px)
                ys.append(sy + py)
        return weight[n] * ((max(xs) - min(xs)) + (max(ys) - min(ys)))

    cost = sum(net_len(n) for n in nets)
    print("start wirelength %.0f mm" % cost)
    movable = list(items)
    t = 60.0
    steps = 400000
    for step in range(steps):
        ref = random.choice(movable)
        kind = items[ref][0]
        j = random.randrange(len(slots[kind]))
        other = occupant[kind][j]
        if other == ref:
            continue
        touched = set(nets_of.get(ref, ())) | (set(nets_of.get(other, ())) if other else set())
        before = sum(net_len(n) for n in touched)
        i = pos[ref]
        pos[ref], occupant[kind][j], occupant[kind][i] = j, ref, other
        if other:
            pos[other] = i
        after = sum(net_len(n) for n in touched)
        delta = after - before
        if delta <= 0 or random.random() < math.exp(-delta / t):
            cost += delta
        else:
            pos[ref], occupant[kind][i], occupant[kind][j] = i, ref, other
            if other:
                pos[other] = j
        if step % 2000 == 0:
            t *= 0.97
        if step % 50000 == 0:
            print("step %6d  T %.2f  wirelength %.0f mm" % (step, t, cost))
    cost = sum(net_len(n) for n in nets)
    print("final wirelength %.0f mm" % cost)

    # ---- write absolute placements (footprint origin + rotation)
    out = {"board": [board_w, board_h], "parts": {}}
    for ref, (kind, rot) in items.items():
        sx, sy = where(ref)
        ox, oy = offs[ref]
        out["parts"][ref] = [round(sx + ox, 3), round(sy + oy, 3), rot]
        for k, cap in enumerate(caps_for.get(ref, [])):
            cl, ct, cr, cb = geom[cap]["box"]
            out["parts"][cap] = [round(sx + 0.8 - cl + k * 8.0, 3), round(sy + 0.3 - ct, 3), 0]
    for ref in FIXED:
        out["parts"][ref] = geom[ref]["at"]
    missing = set(geom) - set(out["parts"])
    assert not missing, missing
    json.dump(out, open(os.path.join(ROOT, "build", "placement.json"), "w"), indent=0)
    print("board %.1f x %.1f mm, %d parts placed" % (board_w, board_h, len(out["parts"])))


if __name__ == "__main__":
    main()
