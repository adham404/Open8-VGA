"""Apply build/placement.json to the KiCad board: move every footprint, remove old copper,
redraw the board outline. Run with KiCad's bundled Python (it has pcbnew).

usage: apply.py <in.kicad_pcb> <placement.json> <out.kicad_pcb>
Author: Adham Elshafei
"""
import json
import sys

import pcbnew


def main(src, placement, dst):
    b = pcbnew.LoadBoard(src)
    pl = json.load(open(placement))
    footprints = list(b.Footprints())
    for t in list(b.Tracks()):
        b.Delete(t)
    for z in list(b.Zones()):
        b.Delete(z)
    for f in footprints:
        x, y, rot = pl["parts"][f.GetReference()]
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    for d in list(b.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            b.Delete(d)
    w, h = pl["board"]
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    for i in range(4):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
        seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        b.Add(seg)
    b.Save(dst)
    print("placed %d footprints, board %.1f x %.1f mm -> %s" % (len(footprints), w, h, dst))


if __name__ == "__main__":
    main(*sys.argv[1:4])
