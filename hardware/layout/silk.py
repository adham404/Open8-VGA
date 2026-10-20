"""Readable silkscreen: each part's reference sits at the centre of its body, along its long
axis, 1.0 mm high (JLCPCB's minimum), and value text is kept off the silkscreen.
The author credits go in the first free area found (front, and mirrored on the back).

Run with KiCad's bundled Python. usage: silk.py <board.kicad_pcb>
Author: Adham Elshafei
"""
import sys

import pcbnew

MM = pcbnew.FromMM


def main(path):
    b = pcbnew.LoadBoard(path)
    for f in b.Footprints():
        ref = f.Reference()
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
        c = bb.GetCenter()
        ref.SetPosition(pcbnew.VECTOR2I(c.x, c.y))
        ref.SetTextSize(pcbnew.VECTOR2I(MM(1.0), MM(1.0)))
        ref.SetTextThickness(MM(0.16))   # JLCPCB minimum line 0.153 mm
        ref.SetTextAngleDegrees(90 if bb.GetHeight() > bb.GetWidth() else 0)
        ref.SetKeepUpright(True)
        ref.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        ref.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        val = f.Value()
        if val.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            val.SetLayer(pcbnew.F_Fab)
    add_credits(b)
    b.Save(path)
    print("relabelled %d parts" % len(b.GetFootprints()))


FRONT = ["Open8-VGA", "Designed by Adham Elshafei", "adham_mohsen@outlook.com", "2026"]
BACK = ["\u00a92026 Adham Elshafei \u2014 Rev A"]


def free_spot(b, w, h):
    """Top-left corner (mm) of a w x h area that no part's courtyard touches, scanning in
    1 mm steps; None if there is no such area."""
    boxes = []
    for f in b.Footprints():
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
        boxes.append((pcbnew.ToMM(bb.GetLeft()) - 1, pcbnew.ToMM(bb.GetTop()) - 1,
                      pcbnew.ToMM(bb.GetRight()) + 1, pcbnew.ToMM(bb.GetBottom()) + 1))
    edge = b.GetBoardEdgesBoundingBox()
    x0, y0 = pcbnew.ToMM(edge.GetLeft()) + 2, pcbnew.ToMM(edge.GetTop()) + 2
    x1, y1 = pcbnew.ToMM(edge.GetRight()) - 2 - w, pcbnew.ToMM(edge.GetBottom()) - 2 - h
    y = y1
    while y >= y0:                      # prefer the bottom of the board
        x = x1
        while x >= x0:                  # and its right-hand side
            if all(x + w < l or x > r or y + h < t or y > bt for l, t, r, bt in boxes):
                return x, y
            x -= 1
        y -= 1
    return None


def add_text(b, layer, lines, x, y, size):
    for k, line in enumerate(lines):
        t = pcbnew.PCB_TEXT(b)
        t.SetText(line)
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(max(0.16, size * 0.15)))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y + k * size * 1.6)))
        if layer == pcbnew.B_SilkS:
            t.SetMirrored(True)         # mirrored text runs leftwards from a left anchor
        b.Add(t)


def add_credits(b):
    for d in list(b.GetDrawings()):
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) \
                and "Adham Elshafei" in d.GetText() or (d.Type() == pcbnew.PCB_TEXT_T and d.GetText() in FRONT):
            b.Delete(d)
    spot = free_spot(b, 50, 4 * 2.0 * 1.6)
    if spot is None:
        raise SystemExit("no free area for the credits")
    add_text(b, pcbnew.F_SilkS, FRONT, spot[0], spot[1] + 1, 2.0)
    add_text(b, pcbnew.B_SilkS, BACK, spot[0] + 50, spot[1] + 1, 2.0)
    print("credits at %.0f, %.0f mm (front and back)" % spot)


if __name__ == "__main__":
    main(sys.argv[1])
