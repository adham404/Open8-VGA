"""Dump footprint geometry (pads at rotation 0, courtyard box) and nets from a KiCad board.
Run with KiCad's bundled Python (it has pcbnew). Author: Adham Elshafei"""
import json, sys
import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
out = {}
for f in b.GetFootprints():
    pos, rot = f.GetPosition(), f.GetOrientationDegrees()
    f.SetOrientationDegrees(0)
    f.SetPosition(pcbnew.VECTOR2I(0, 0))
    bb = f.GetCourtyard(pcbnew.F_CrtYd).BBox() if f.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else f.GetBoundingBox(False)
    pads = [{"num": p.GetNumber(), "x": pcbnew.ToMM(p.GetPosition().x), "y": pcbnew.ToMM(p.GetPosition().y),
             "net": p.GetNetname()} for p in f.Pads()]
    out[f.GetReference()] = {"fp": f.GetFPIDAsString(), "value": f.GetValue(),
                             "box": [pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                                     pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())],
                             "pads": pads, "at": [pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), rot]}
    f.SetOrientationDegrees(rot)
    f.SetPosition(pos)
json.dump(out, open(sys.argv[2], "w"), indent=0)
print(len(out), "footprints")
