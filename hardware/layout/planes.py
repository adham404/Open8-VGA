"""Finish the power distribution on the routed 6-layer board.

* Surface-mount pads on VCC or GND get a 0.5 mm track to a via, so they reach the planes
  (every through-hole pin reaches them already). Each via goes on the nearest spot that
  clears all other-net copper on every layer.
* The VGA connector's GND pins connect solid (its pin pitch leaves no room for spokes).
* In1.Cu is poured as the GND plane and In4.Cu as the VCC plane, over the whole board.

Run with KiCad's bundled Python. usage: planes.py <board.kicad_pcb>
Author: Adham Elshafei
"""
import math
import sys

import pcbnew

# surface-mount pads on VCC/GND that need a via down to their plane
POWER_PADS = [("F1", "1"), ("F2", "2"), ("D2", "1"), ("D2", "2"), ("J3", "A12"), ("J3", "B12")]
# pads whose pin pitch leaves no room for thermal spokes: connect them solid to the plane
SOLID_PADS = [("J2", n) for n in ("5", "6", "7", "8", "10")]
PLANES = [("GND", pcbnew.In1_Cu), ("VCC", pcbnew.In4_Cu)]
MM = pcbnew.FromMM
VIA_D, VIA_DRILL, LINK_W, GAP = 0.6, 0.3, 0.5, 0.25


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def seg_seg_dist(a, b, c, d):
    return min(seg_dist(*a, *c, *d), seg_dist(*b, *c, *d), seg_dist(*c, *a, *b), seg_dist(*d, *a, *b))


def obstacles(b, net):
    """Other-net copper as (kind, geometry, half-width, on_front) in mm."""
    out = []
    mm = pcbnew.ToMM
    for t in b.Tracks():
        if t.GetNetname() == net:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            out.append(("pt", (mm(p.x), mm(p.y)), mm(t.GetWidth(pcbnew.F_Cu)) / 2, True))
        else:
            s0, s1 = t.GetStart(), t.GetEnd()
            out.append(("seg", ((mm(s0.x), mm(s0.y)), (mm(s1.x), mm(s1.y))), mm(t.GetWidth()) / 2,
                        t.GetLayer() == pcbnew.F_Cu))
    for f in b.Footprints():
        for p in f.Pads():
            if p.GetNetname() == net:
                continue
            bb = p.GetBoundingBox()
            c = p.GetPosition()
            r = max(mm(bb.GetWidth()), mm(bb.GetHeight())) / 2
            out.append(("pt", (mm(c.x), mm(c.y)), r, p.IsOnLayer(pcbnew.F_Cu)))
    return out


def free(obs, via, pad):
    vr = VIA_D / 2
    for kind, geo, hw, front in obs:
        if kind == "pt":
            if math.hypot(via[0] - geo[0], via[1] - geo[1]) < vr + hw + GAP:
                return False
            if front and seg_dist(geo[0], geo[1], *pad, *via) < LINK_W / 2 + hw + GAP:
                return False
        else:
            if seg_dist(via[0], via[1], *geo[0], *geo[1]) < vr + hw + GAP:
                return False
            if front and seg_seg_dist(pad, via, geo[0], geo[1]) < LINK_W / 2 + hw + GAP:
                return False
    return True


def add_power_vias(b):
    pads = {(f.GetReference(), p.GetNumber()): p for f in b.Footprints() for p in f.Pads()}
    box = b.GetBoardEdgesBoundingBox()
    for ref, num in POWER_PADS:
        pad = pads[(ref, num)]
        net = pad.GetNetname()
        obs = obstacles(b, net)
        c = pad.GetPosition()
        pc = (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))
        spot = None
        for r in [x * 0.25 for x in range(6, 25)]:          # 1.5 .. 6 mm away
            for k in range(24):
                a = 2 * math.pi * k / 24
                v = (pc[0] + r * math.cos(a), pc[1] + r * math.sin(a))
                if not (pcbnew.ToMM(box.GetLeft()) + 1 < v[0] < pcbnew.ToMM(box.GetRight()) - 1 and
                        pcbnew.ToMM(box.GetTop()) + 1 < v[1] < pcbnew.ToMM(box.GetBottom()) - 1):
                    continue
                if free(obs, v, pc):
                    spot = v
                    break
            if spot:
                break
        if not spot:
            raise SystemExit("no free via spot near %s.%s" % (ref, num))
        end = pcbnew.VECTOR2I(MM(spot[0]), MM(spot[1]))
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(end)
        via.SetWidth(MM(VIA_D))
        via.SetDrill(MM(VIA_DRILL))
        via.SetNet(pad.GetNet())
        b.Add(via)
        trk = pcbnew.PCB_TRACK(b)
        trk.SetStart(c)
        trk.SetEnd(end)
        trk.SetWidth(MM(LINK_W))
        trk.SetLayer(pcbnew.F_Cu)
        trk.SetNet(pad.GetNet())
        b.Add(trk)
        print("via for %s.%s (%s) at %.2f, %.2f" % (ref, num, net, spot[0], spot[1]))
    for ref, num in SOLID_PADS:
        pads[(ref, num)].SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)


def add_planes(b):
    box = b.GetBoardEdgesBoundingBox()
    inset = MM(0.5)
    pts = [(box.GetLeft() + inset, box.GetTop() + inset), (box.GetRight() - inset, box.GetTop() + inset),
           (box.GetRight() - inset, box.GetBottom() - inset), (box.GetLeft() + inset, box.GetBottom() - inset)]
    for net, layer in PLANES:
        z = pcbnew.ZONE(b)
        z.SetLayer(layer)
        z.SetNetCode(b.FindNet(net).GetNetCode())
        z.SetLocalClearance(MM(0.25))
        z.SetMinThickness(MM(0.25))
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIsFilled(False)
        outline = z.Outline()
        outline.NewOutline()
        for x, y in pts:
            outline.Append(x, y)
        z.SetZoneName("%s plane" % net)
        b.Add(z)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())


def main(path):
    b = pcbnew.LoadBoard(path)
    for z in list(b.Zones()):
        b.Delete(z)
    add_power_vias(b)
    add_planes(b)
    b.Save(path)
    for z in b.Zones():
        print("%s: %d filled polygon(s) on %s" % (z.GetZoneName(), z.GetFilledPolysList(z.GetLayer()).OutlineCount(),
                                                b.GetLayerName(z.GetLayer())))


if __name__ == "__main__":
    main(sys.argv[1])
