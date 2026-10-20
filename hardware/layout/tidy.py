"""Tidy the routed copper before the planes go in.

* Every via becomes a through via (F.Cu to B.Cu). The session import marks Freerouting's vias
  blind/buried because the plane layers were hidden from it; JLCPCB would charge for those.
* Track stubs shorter than 0.02 mm (left over from the session import) are deleted.
* Tracks thinner than 0.127 mm (Freerouting's neck-downs at pins) are widened to 0.127 mm,
  except where that would break the 0.127 mm clearance; those keep their width if it is at
  least JLCPCB's 0.09 mm 6-layer minimum, else get exactly 0.09 mm.

Run with KiCad's bundled Python. usage: tidy.py <board.kicad_pcb>
Author: Adham Elshafei
"""
import math
import sys

import pcbnew

MM, TO = pcbnew.FromMM, pcbnew.ToMM
TARGET, FLOOR, CLEAR = 0.127, 0.09, 0.127


def seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def seg_seg(a, b, c, d):
    return min(seg_dist(a, c, d), seg_dist(b, c, d), seg_dist(c, a, b), seg_dist(d, a, b))


def main(path):
    b = pcbnew.LoadBoard(path)
    through = stubs = 0
    for t in list(b.Tracks()):
        if t.Type() == pcbnew.PCB_VIA_T:
            if t.GetViaType() != pcbnew.VIATYPE_THROUGH:
                t.SetViaType(pcbnew.VIATYPE_THROUGH)
                t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                through += 1
        elif TO(t.GetLength()) < 0.02:
            b.Delete(t)
            stubs += 1
    # neighbours by layer for the clearance test
    items = []
    for t in b.Tracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            items.append(("via", None, (TO(p.x), TO(p.y)), None, TO(t.GetWidth(pcbnew.F_Cu)) / 2, t.GetNetCode()))
        else:
            s, e = t.GetStart(), t.GetEnd()
            items.append(("trk", t.GetLayer(), (TO(s.x), TO(s.y)), (TO(e.x), TO(e.y)), TO(t.GetWidth()) / 2,
                          t.GetNetCode()))
    for f in b.Footprints():
        for p in f.Pads():
            bb = p.GetBoundingBox()
            c = p.GetPosition()
            items.append(("pad", p, (TO(c.x), TO(c.y)), None,
                          max(TO(bb.GetWidth()), TO(bb.GetHeight())) / 2, p.GetNetCode()))
    widened = kept = floored = 0
    for t in b.Tracks():
        if t.Type() == pcbnew.PCB_VIA_T or TO(t.GetWidth()) >= TARGET - 1e-6:
            continue
        s, e = t.GetStart(), t.GetEnd()
        a, c = (TO(s.x), TO(s.y)), (TO(e.x), TO(e.y))
        net, layer = t.GetNetCode(), t.GetLayer()
        room = 99.0
        for kind, lay, p0, p1, r, n in items:
            if n == net:
                continue
            if kind == "trk":
                if lay != layer:
                    continue
                d = seg_seg(a, c, p0, p1) - r
            elif kind == "pad":
                if not lay.IsOnLayer(layer):
                    continue
                d = seg_dist(p0, a, c) - r
            else:
                d = seg_dist(p0, a, c) - r
            room = min(room, d)
        best = 2 * (room - CLEAR)          # widest track that keeps the clearance
        if best >= TARGET:
            t.SetWidth(MM(TARGET))
            widened += 1
        elif TO(t.GetWidth()) >= FLOOR:
            kept += 1
        else:
            t.SetWidth(MM(FLOOR))
            floored += 1
    b.Save(path)
    print("vias made through: %d, stubs removed: %d" % (through, stubs))
    print("thin tracks: %d widened to %.3f mm, %d kept (>= %.2f mm), %d set to %.2f mm"
          % (widened, TARGET, kept, FLOOR, floored, FLOOR))


if __name__ == "__main__":
    main(sys.argv[1])
