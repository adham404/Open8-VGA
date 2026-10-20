"""Finish the last open signal connections with a grid maze router (A*).

Freerouting leaves a handful of connections it cannot place; this routes them one by one on
the four signal layers (F.Cu, In2.Cu, In3.Cu, B.Cu), keeping the board's clearance from all
other-net copper, with through vias where it changes layer. Open connections are read from a
KiCad DRC report (JSON).

Run with KiCad's bundled Python.
usage: maze.py <board.kicad_pcb> <drc.json>
Author: Adham Elshafei
"""
import heapq
import json
import math
import re
import sys
from array import array

import pcbnew

G = 0.1                     # grid pitch, mm
TRACK_W, CLEAR = 0.127, 0.127
VIA_D, VIA_DRILL = 0.45, 0.3
VIA_COST = 30.0             # in grid steps (3 mm of track)
EDGE = 0.4
SIGNAL = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu]
BLOCKED = 65535
MM = pcbnew.FromMM


class Grid:
    def __init__(self, b):
        self.b = b
        box = b.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = pcbnew.ToMM(box.GetLeft()), pcbnew.ToMM(box.GetTop())
        self.w = int(pcbnew.ToMM(box.GetWidth()) / G) + 1
        self.h = int(pcbnew.ToMM(box.GetHeight()) / G) + 1
        self.cells = [array("H", bytes(2 * self.w * self.h)) for _ in SIGNAL]
        self.layer_index = {l: i for i, l in enumerate(SIGNAL)}
        self.drill = bytearray(self.w * self.h)
        rr = int(math.ceil((VIA_D - TRACK_W) / 2 / G))
        self.via_ring = [dy * self.w + dx for dy in range(-rr, rr + 1) for dx in range(-rr, rr + 1)
                         if dx * dx + dy * dy <= rr * rr]
        e = int(EDGE / G) + 1
        for li in range(len(SIGNAL)):
            c = self.cells[li]
            for y in range(self.h):
                for x in list(range(e)) + list(range(self.w - e, self.w)):
                    c[y * self.w + x] = BLOCKED
            for x in range(self.w):
                for y in list(range(e)) + list(range(self.h - e, self.h)):
                    c[y * self.w + x] = BLOCKED

    def mark(self, li, idx, net):
        c = self.cells[li]
        v = c[idx]
        if v == 0:
            c[idx] = net + 1
        elif v != net + 1:
            c[idx] = BLOCKED

    def disc(self, li, cx, cy, r, net):
        gx, gy, gr = (cx - self.x0) / G, (cy - self.y0) / G, r / G
        for y in range(max(0, int(gy - gr)), min(self.h, int(gy + gr) + 2)):
            dy = y - gy
            if abs(dy) > gr:
                continue
            dx = math.sqrt(gr * gr - dy * dy)
            for x in range(max(0, int(gx - dx)), min(self.w, int(gx + dx) + 2)):
                if (x - gx) ** 2 + dy * dy <= gr * gr:
                    self.mark(li, y * self.w + x, net)

    def segment(self, li, ax, ay, bx, by, r, net):
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(L / (G * 0.5)))
        for k in range(n + 1):
            t = k / n
            self.disc(li, ax + (bx - ax) * t, ay + (by - ay) * t, r, net)

    def rect(self, li, cx, cy, hw, hh, r, net):
        x0, x1 = int((cx - hw - r - self.x0) / G), int((cx + hw + r - self.x0) / G) + 1
        y0, y1 = int((cy - hh - r - self.y0) / G), int((cy + hh + r - self.y0) / G) + 1
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.mark(li, y * self.w + x, net)

    def load(self):
        """Every copper item, inflated so a track centre on a free cell keeps clearance."""
        mm = pcbnew.ToMM
        infl = TRACK_W / 2 + CLEAR
        for t in self.b.Tracks():
            net = t.GetNetCode()
            if t.Type() == pcbnew.PCB_VIA_T:
                p = t.GetPosition()
                self.block_drill(mm(p.x), mm(p.y), mm(t.GetDrillValue()) / 2)
                for li in range(len(SIGNAL)):
                    self.disc(li, mm(p.x), mm(p.y), mm(t.GetWidth(pcbnew.F_Cu)) / 2 + infl, net)
            elif t.GetLayer() in self.layer_index:
                s0, s1 = t.GetStart(), t.GetEnd()
                self.segment(self.layer_index[t.GetLayer()], mm(s0.x), mm(s0.y), mm(s1.x), mm(s1.y),
                             mm(t.GetWidth()) / 2 + infl, net)
        for f in self.b.Footprints():
            for p in f.Pads():
                net = p.GetNetCode()
                bb = p.GetBoundingBox()
                c = bb.GetCenter()
                hw, hh = mm(bb.GetWidth()) / 2, mm(bb.GetHeight()) / 2
                round_pad = p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE
                if p.GetDrillSize().x > 0:
                    pc = p.GetPosition()
                    self.block_drill(mm(pc.x), mm(pc.y), mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2)
                for l in SIGNAL:
                    if p.IsOnLayer(l):
                        li = self.layer_index[l]
                        if round_pad:
                            self.disc(li, mm(c.x), mm(c.y), hw + infl, net)
                        else:
                            self.rect(li, mm(c.x), mm(c.y), hw, hh, infl, net)

    def idx(self, x, y):
        return int(round((y - self.y0) / G)) * self.w + int(round((x - self.x0) / G))

    def free(self, li, i, net):
        v = self.cells[li][i]
        return v == 0 or v == net + 1

    def via_ok(self, i, net):
        """A via (0.45 mm) needs (0.45 - 0.127) / 2 = 0.16 mm more room than a track on every
        signal layer, and its drill must keep JLCPCB's 0.5 mm from every other hole."""
        if self.drill[i]:
            return False
        for li in range(len(SIGNAL)):
            for d in self.via_ring:
                if not self.free(li, i + d, net):
                    return False
        return True

    def block_drill(self, cx, cy, hole_r):
        """No new via centre within hole_r + 0.5 mm + via drill radius of this hole."""
        r = (hole_r + 0.5 + VIA_DRILL / 2) / G
        gx, gy = (cx - self.x0) / G, (cy - self.y0) / G
        for y in range(max(0, int(gy - r)), min(self.h, int(gy + r) + 2)):
            for x in range(max(0, int(gx - r)), min(self.w, int(gx + r) + 2)):
                if (x - gx) ** 2 + (y - gy) ** 2 <= r * r:
                    self.drill[y * self.w + x] = 1


def route(g, net, start, goal):
    """start/goal: (x, y, [layer indices]). Returns list of (layer index, cell index)."""
    w = g.w
    gi = g.idx(goal[0], goal[1])
    gx, gy = gi % w, gi // w
    goal_states = {(li, gi) for li in goal[2]}
    si = g.idx(start[0], start[1])
    heap, best, prev = [], {}, {}
    for li in start[2]:
        best[(li, si)] = 0.0
        heapq.heappush(heap, (0.0, 0.0, li, si))
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    expanded = 0
    while heap:
        f, cost, li, i = heapq.heappop(heap)
        if cost > best.get((li, i), 1e18):
            continue
        if (li, i) in goal_states:
            path = [(li, i)]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1]
        expanded += 1
        if expanded > 3000000:
            return None
        x, y = i % w, i // w
        for dx, dy, c in moves:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < g.h):
                continue
            ni = ny * w + nx
            if dx and dy and not (g.free(li, y * w + nx, net) and g.free(li, ny * w + x, net)):
                continue
            if not g.free(li, ni, net):
                continue
            nc = cost + c
            if nc < best.get((li, ni), 1e18):
                best[(li, ni)] = nc
                prev[(li, ni)] = (li, i)
                ddx, ddy = abs(nx - gx), abs(ny - gy)
                h = max(ddx, ddy) + 0.414 * min(ddx, ddy)
                heapq.heappush(heap, (nc + 1.15 * h, nc, li, ni))
        if g.via_ok(i, net):
            for lj in range(len(SIGNAL)):
                if lj != li:
                    nc = cost + VIA_COST
                    if nc < best.get((lj, i), 1e18):
                        best[(lj, i)] = nc
                        prev[(lj, i)] = (li, i)
                        ddx, ddy = abs(x - gx), abs(y - gy)
                        h = max(ddx, ddy) + 0.414 * min(ddx, ddy)
                        heapq.heappush(heap, (nc + 1.15 * h, nc, lj, i))
    return None


def emit(g, b, netinfo, path, start_xy, goal_xy):
    """Turn a cell path into KiCad tracks and vias; also mark them in the grid."""
    w = g.w
    pts = []
    for li, i in path:
        pts.append((li, g.x0 + (i % w) * G, g.y0 + (i // w) * G))
    pts[0] = (pts[0][0], start_xy[0], start_xy[1])
    pts[-1] = (pts[-1][0], goal_xy[0], goal_xy[1])
    net = netinfo.GetNetCode()
    infl = TRACK_W / 2 + CLEAR
    # split into runs per layer, collapse collinear points
    k = 0
    n_tracks = n_vias = 0
    while k < len(pts) - 1:
        li = pts[k][0]
        run = [pts[k]]
        while k + 1 < len(pts) and pts[k + 1][0] == li:
            k += 1
            run.append(pts[k])
        simp = [run[0]]
        for p in run[1:-1]:
            a, c = simp[-1], p
            nxt = run[run.index(p) + 1]
            d1 = (round((c[1] - a[1]) / G), round((c[2] - a[2]) / G))
            d2 = (round((nxt[1] - c[1]) / G), round((nxt[2] - c[2]) / G))
            if d1[0] * d2[1] != d1[1] * d2[0] or d1[0] * d2[0] + d1[1] * d2[1] < 0:
                simp.append(c)
        simp.append(run[-1])
        for a, c in zip(simp, simp[1:]):
            if math.hypot(c[1] - a[1], c[2] - a[2]) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(MM(a[1]), MM(a[2])))
            t.SetEnd(pcbnew.VECTOR2I(MM(c[1]), MM(c[2])))
            t.SetWidth(MM(TRACK_W))
            t.SetLayer(SIGNAL[li])
            t.SetNet(netinfo)
            b.Add(t)
            g.segment(li, a[1], a[2], c[1], c[2], TRACK_W / 2 + infl, net)
            n_tracks += 1
        if k + 1 < len(pts):            # layer change here: a through via
            x, y = pts[k + 1][1], pts[k + 1][2]
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
            v.SetWidth(MM(VIA_D))
            v.SetDrill(MM(VIA_DRILL))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetNet(netinfo)
            b.Add(v)
            for lj in range(len(SIGNAL)):
                g.disc(lj, x, y, VIA_D / 2 + infl, net)
            g.block_drill(x, y, VIA_DRILL / 2)
            n_vias += 1
            k += 1
    return n_tracks, n_vias


def endpoint(item, layer_index):
    desc, pos = item["description"], item["pos"]
    m = re.search(r" on (\w+\.Cu)", desc)
    if desc.startswith("Track") and m:
        layers = [layer_index[pcbnew.BOARD.GetLayerID(BOARD, m.group(1))]]
    else:
        layers = list(range(len(SIGNAL)))
    return (pos["x"], pos["y"], layers)


BOARD = None


def main(path, drc):
    global BOARD
    b = pcbnew.LoadBoard(path)
    BOARD = b
    g = Grid(b)
    g.load()
    report = json.load(open(drc))
    done = failed = 0
    for u in report["unconnected_items"]:
        a, c = u["items"]
        netname = re.search(r"\[([^\]]+)\]", a["description"]).group(1)
        if netname in ("GND", "VCC"):
            continue
        ni = b.FindNet(netname)
        s, e = endpoint(a, g.layer_index), endpoint(c, g.layer_index)
        p = route(g, ni.GetNetCode(), s, e)
        if not p:
            print("FAILED %s %s -> %s" % (netname, s[:2], e[:2]))
            failed += 1
            continue
        nt, nv = emit(g, b, ni, p, s[:2], e[:2])
        print("routed %-8s %3d segments, %d vias" % (netname, nt, nv))
        done += 1
    b.Save(path)
    print("%d routed, %d failed" % (done, failed))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
