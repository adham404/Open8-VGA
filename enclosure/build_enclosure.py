"""Open8-VGA enclosure: a compact-Macintosh-style case, generated in FreeCAD.

Run with FreeCAD's command-line interpreter (no GUI needed):

    enclosure/run_freecad.sh enclosure/build_enclosure.py

Inputs:  build/enclosure/open8-vga-board.step  (kicad-cli pcb export step, see README)
Outputs: enclosure/out/  one STL per printed part, the assembly as STEP, and the
         FreeCAD document open8-vga-enclosure.FCStd with every part plus the board and
         LCD panel as reference models. A fit report is printed and written to
         enclosure/out/fit_report.txt.

Coordinates (mm): X = width (left to right, seen from the front), Y = depth (front to
back), Z = height. Origin at the front-left-bottom corner.

Layout: the logic board stands on the left wall with its components facing out and its
connector edge at the back; a magnetic door in the left wall opens onto the board's control
strip (buttons, slide switches, jumpers, logic-analyser headers). The LCD sits behind the
screen bezel; its driver board sits on a tray in the chin.

Author: Adham Elshafei
"""
import math
import os
import sys

import FreeCAD
import Part
from FreeCAD import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
BOARD_STEP = os.path.join(ROOT, "build", "enclosure", "open8-vga-board.step")

# ---------------------------------------------------------------- parameters
P = dict(
    W=250.0, H=340.0, D=345.0,      # outside size
    T=3.5,                          # wall thickness
    R=10.0,                         # front-outline corner radius
    BZ=6.0,                         # bezel thickness (Y 0..BZ)
    Z_CHIN=120.0,                   # chin line: bezel split and shell split height
    Y_SPLIT=175.0,                  # shell split depth
    LIP=8.0, LIP_T=6.0,             # seam lips: depth inward, thickness
    BED=256.0,                      # printer bed (X, Y and height)
    # LCD: 8" 800x600 (Innolux AT080TN52-class): outline, active area, thickness
    PANEL_W=183.0, PANEL_H=141.0, PANEL_T=5.6,
    ACTIVE_W=162.0, ACTIVE_H=121.5,
    ACTIVE_DX=0.0, ACTIVE_DZ=0.0,   # active-area centre offset in the outline (check drawing)
    SCREEN_TOP_MARGIN=50.0,         # outside top to top of the visible window
    SURROUND=14.0,                  # recessed screen surround around the window
    FPC_NOTCH_W=70.0,               # clamp-frame notch for the panel's flex cable (bottom)
    # logic board (Rev A): 313.1 x 259.6 x 1.6
    PCB_L=313.1, PCB_H=259.6, PCB_T=1.6,
    COMP_CLEAR=3.0,                 # tallest component to wall gap
    RAIL_SLOT=2.0, RAIL_DEPTH=2.5, RAIL_CHEEK=4.0,
    BACK_GAP=1.0,                   # board edge to back wall
    # controls door (board coordinates of the strip it exposes, mm from the connector edge)
    DOOR_PX=(5.0, 50.0), DOOR_PY=(0.0, 257.0), DOOR_LEDGE=4.0, DOOR_LEDGE_T=2.0,
    MAGNET_D=6.2, MAGNET_H=3.2,
    # driver-board tray in the chin
    TRAY=(150.0, 100.0), TRAY_POS=(60.0, 25.0), TRAY_POST_H=12.0,
    # back panel extras
    DC_JACK_D=11.2, DC_JACK_POS=(210.0, 60.0),
    PS2_OPEN=1.5,                   # PS/2 opening: margin around J1's body for the plug's overmould
    INSERT_D=4.0, INSERT_DEPTH=5.0, CLEAR_D=3.4,
    # mid-depth join: the front and rear halves are built separately, then pulled together
    # by 4 M3 rods from the back panel into inserts in the front half; a lap-joint tongue
    # on the rear half aligns the walls
    ROD_PTS=((35.0, 8.5), (35.0, 331.5), (215.0, 8.5), (215.0, 331.5)),   # (X, Z)
    ROD_BOSS_D=10.0, ROD_BOSS_LEN=18.0, ROD_BORE_D=3.6, ROD_CBORE_D=8.0,
    TONGUE=(1.9, 3.4, 5.0),         # tongue: from / to inset from the outside, length
    TONGUE_GAP=0.2,                 # rebate clearance around the tongue
)
globals().update(P)


# ---------------------------------------------------------------- helpers
def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def rbox_y(x0, y0, z0, x1, y1, z1, r):
    """Box whose edges parallel to Y are rounded (rounded rectangle in X-Z, along Y)."""
    b = box(x0, y0, z0, x1, y1, z1)
    if r <= 0:
        return b
    edges = [e for e in b.Edges
             if abs(e.Vertexes[0].X - e.Vertexes[1].X) < 1e-6
             and abs(e.Vertexes[0].Z - e.Vertexes[1].Z) < 1e-6]
    return b.makeFillet(r, edges)


def rbox_x(x0, y0, z0, x1, y1, z1, r):
    """Box whose edges parallel to X are rounded (rounded rectangle in Y-Z)."""
    b = box(x0, y0, z0, x1, y1, z1)
    edges = [e for e in b.Edges
             if abs(e.Vertexes[0].Y - e.Vertexes[1].Y) < 1e-6
             and abs(e.Vertexes[0].Z - e.Vertexes[1].Z) < 1e-6]
    return b.makeFillet(r, edges)


def cyl_y(x, z, r, y0, y1):
    return Part.makeCylinder(r, y1 - y0, V(x, y0, z), V(0, 1, 0))


def cyl_x(y, z, r, x0, x1):
    return Part.makeCylinder(r, x1 - x0, V(x0, y, z), V(1, 0, 0))


def cyl_z(x, y, r, z0, z1):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0), V(0, 0, 1))


def prism_x(pts_yz, x0, x1):
    """Extrude a Y-Z polygon along X."""
    w = Part.makePolygon([V(x0, y, z) for y, z in pts_yz] + [V(x0, pts_yz[0][0], pts_yz[0][1])])
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


def prism_y(pts_xz, y0, y1):
    w = Part.makePolygon([V(x, y0, z) for x, z in pts_xz] + [V(pts_xz[0][0], y0, pts_xz[0][1])])
    return Part.Face(w).extrude(V(0, y1 - y0, 0))


def fuse(shapes):
    s = shapes[0]
    if len(shapes) > 1:
        s = s.fuse(shapes[1:])
    return s.removeSplitter()


def cut(s, tools):
    tools = [t for t in tools if t is not None]
    return s.cut(Part.makeCompound(tools)).removeSplitter() if tools else s


def spaced(a, b, pitch):
    """Evenly spaced positions strictly inside (a, b), about `pitch` apart."""
    n = max(1, int(round((b - a) / pitch)))
    return [a + (b - a) * (i + 0.5) / n for i in range(n)]


# ---------------------------------------------------------------- the board
# parts KiCad has no 3D model for: PCB courtyard (x0, x1 from the connector edge, y0, y1
# down from the top) and height
STAND_INS = {
    "J1": ((4.2, 17.8, 220.8, 236.2), 13.0),    # MD-60SM PS/2 jack, opening toward the edge
    "RV1": ((31.3, 41.4, 19.2, 29.3), 10.0),    # Bourns 3386P trimmer
}


def load_board():
    """Board STEP placed in case coordinates, plus stand-ins for parts KiCad has no 3D
    model for. Returns (shape, placement info)."""
    raw = Part.read(BOARD_STEP)
    bb = raw.BoundBox
    zmax = max(bb.ZMax, PCB_T + 13.0)            # J1 stand-in is 13 mm tall
    xb = T + (zmax - PCB_T) + COMP_CLEAR         # component-side surface of the board
    yb = D - T - BACK_GAP                        # connector edge
    z_bb = T + 19.0 - RAIL_DEPTH                 # bottom edge, inside the bottom rail
    z_bt = z_bb + PCB_H                          # top edge
    # STEP (x right, y up, z = component side) -> case: X = xb + 1.6 - z, Y = yb - x, Z = z_bt + y
    m = FreeCAD.Matrix()
    m.A11, m.A12, m.A13, m.A14 = 0, 0, -1, xb + PCB_T
    m.A21, m.A22, m.A23, m.A24 = -1, 0, 0, yb
    m.A31, m.A32, m.A33, m.A34 = 0, 1, 0, z_bt
    parts = [raw]
    for (x0, x1, y0, y1), h in STAND_INS.values():
        parts.append(box(x0, -y1, PCB_T, x1, -y0, PCB_T + h))
    shape = Part.makeCompound(parts)
    shape = shape.transformGeometry(m)
    info = dict(xb=xb, yb=yb, z_bb=z_bb, z_bt=z_bt, zmax=zmax, raw_bb=bb)
    return shape, info


def pcb_body(board):
    """The bare circuit board: the board solid with the largest footprint."""
    return max(board.Solids, key=lambda s: s.BoundBox.YLength * s.BoundBox.ZLength)


def check_solids(ref):
    """Solids to test for overlaps. The bare PCB is tested as its outline box: OCC's
    boolean on a board with thousands of drill holes gives false slivers."""
    out = []
    pcb = pcb_body(ref) if ref.BoundBox.YLength > 300 else None
    for s in ref.Solids or [ref]:
        if pcb is not None and s.isSame(pcb):
            bb = s.BoundBox
            s = box(bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
        out.append(s)
    return out


def pcb_to_case(info, px, py):
    """Board coordinates (mm from the connector edge, mm down from the top) -> (Y, Z)."""
    return info["yb"] - px, info["z_bt"] - py


# ---------------------------------------------------------------- LCD panel
def panel_geometry():
    cx = W / 2
    win_w, win_h = ACTIVE_W + 1.0, ACTIVE_H + 1.0
    win_top = H - SCREEN_TOP_MARGIN
    wcz = win_top - win_h / 2                       # window centre
    pcx, pcz = cx - ACTIVE_DX, wcz - ACTIVE_DZ      # panel outline centre
    return dict(cx=cx, wcz=wcz, win_w=win_w, win_h=win_h, pcx=pcx, pcz=pcz)


def panel_model(g):
    y0 = BZ - 2.0                                    # sits in a 2 mm pocket in the bezel
    return box(g["pcx"] - PANEL_W / 2, y0, g["pcz"] - PANEL_H / 2,
               g["pcx"] + PANEL_W / 2, y0 + PANEL_T, g["pcz"] + PANEL_H / 2)


def clamp_boss_positions(g):
    dx, dz = PANEL_W / 2 + 6.0, PANEL_H / 2 + 6.0
    return [(g["pcx"] + sx * dx, g["pcz"] + sz * dz) for sx in (-1, 1) for sz in (-1, 1)]


# ---------------------------------------------------------------- bezel
def bezel_parts(g):
    face = rbox_y(0, 0, 0, W, BZ, H, R)
    # recessed screen surround and the window
    sw, sh = g["win_w"] + 2 * SURROUND, g["win_h"] + 2 * SURROUND
    surround = rbox_y(g["cx"] - sw / 2, -1, g["wcz"] - sh / 2,
                      g["cx"] + sw / 2, 2.0, g["wcz"] + sh / 2, 8.0)
    window = rbox_y(g["cx"] - g["win_w"] / 2, -1, g["wcz"] - g["win_h"] / 2,
                    g["cx"] + g["win_w"] / 2, BZ + 1, g["wcz"] + g["win_h"] / 2, 2.0)
    pocket = box(g["pcx"] - PANEL_W / 2 - 0.3, BZ - 2.0, g["pcz"] - PANEL_H / 2 - 0.3,
                 g["pcx"] + PANEL_W / 2 + 0.3, BZ + 1, g["pcz"] + PANEL_H / 2 + 0.3)
    face = cut(face, [surround, window, pocket])
    # clamp-frame bosses (panel thickness minus pocket, plus 0.4 for a foam gasket)
    boss_len = PANEL_T - 2.0 + 0.4
    bosses = [cyl_y(x, z, 3.5, BZ - 0.1, BZ + boss_len) for x, z in clamp_boss_positions(g)]
    face = fuse([face] + bosses)
    face = cut(face, [cyl_y(x, z, INSERT_D / 2, BZ + boss_len - INSERT_DEPTH - 1, BZ + boss_len + 1)
                      for x, z in clamp_boss_positions(g)])
    # inserts for the shell's front lip screws (into the bezel rim, from the back)
    face = cut(face, [cyl_y(x, z, INSERT_D / 2, BZ - INSERT_DEPTH, BZ + 1)
                      for x, z in front_lip_screws()])
    # split on the chin line, with a small V on both edges (the line in the sketch)
    v = 0.8
    groove = prism_y([(0, Z_CHIN - v), (W, Z_CHIN - v), (W, Z_CHIN + v), (0, Z_CHIN + v)], -1, 0.8)
    face = cut(face, [groove])
    upper = face.common(box(-1, -1, Z_CHIN + 0.25, W + 1, BZ + 20, H + 1)).removeSplitter()
    chin = face.common(box(-1, -1, -1, W + 1, BZ + 20, Z_CHIN - 0.25)).removeSplitter()
    return upper, chin


def front_lip_screws():
    """Screw positions (X, Z) around the front lip ring, 5 mm in from the inner wall."""
    c = T + LIP / 2
    pts = []
    for x in spaced(30, W - 30, 60):
        pts += [(x, c), (x, H - c)]
    for z in spaced(30, H - 30, 60):
        if abs(z - Z_CHIN) > 12:
            pts += [(c, z), (W - c, z)]
    pts += [(c, Z_CHIN - 9), (W - c, Z_CHIN - 9), (c, Z_CHIN + 9), (W - c, Z_CHIN + 9)]
    return pts


def clamp_frame(g):
    o = 12.0
    outer = box(g["pcx"] - PANEL_W / 2 - o, 0, g["pcz"] - PANEL_H / 2 - o,
                g["pcx"] + PANEL_W / 2 + o, 3.0, g["pcz"] + PANEL_H / 2 + o)
    inner = box(g["pcx"] - PANEL_W / 2 + 6, -1, g["pcz"] - PANEL_H / 2 + 6,
                g["pcx"] + PANEL_W / 2 - 6, 4.0, g["pcz"] + PANEL_H / 2 - 6)
    notch = box(g["pcx"] - FPC_NOTCH_W / 2, -1, g["pcz"] - PANEL_H / 2 - o - 1,
                g["pcx"] + FPC_NOTCH_W / 2, 4.0, g["pcz"] - PANEL_H / 2 + 7)
    f = cut(outer, [inner, notch] +
            [cyl_y(x, z, CLEAR_D / 2, -1, 4) for x, z in clamp_boss_positions(g)])
    y0 = BZ + PANEL_T - 2.0 + 0.4
    f.translate(V(0, y0, 0))
    return f


# ---------------------------------------------------------------- shell
HARDWARE = {}


def shell(info, g, board):
    outer = rbox_y(0, BZ, 0, W, D, H, R)
    inner = rbox_y(T, BZ - 1, T, W - T, D - T, H - T, R - T)
    s = outer.cut(inner)
    adds, cuts = [], []
    # front lip ring (the bezel screws to it)
    ring = cut(rbox_y(T, BZ, T, W - T, BZ + 5, H - T, R - T),
               [rbox_y(T + LIP, BZ - 1, T + LIP, W - T - LIP, BZ + 6, H - T - LIP, 2)])
    adds.append(ring)
    cuts += [cyl_y(x, z, CLEAR_D / 2, BZ - 1, BZ + 6) for x, z in front_lip_screws()]
    # horizontal seam lips at the chin line (left, right, back walls) with 45-degree gussets
    zc, lt, lp = Z_CHIN, LIP_T, LIP
    for side in ("L", "R"):
        x_in = T if side == "L" else W - T
        sgn = 1 if side == "L" else -1
        lower = [(x_in, zc - lt - lp), (x_in, zc), (x_in + sgn * lp, zc), (x_in + sgn * lp, zc - lt)]
        upper = [(x_in, zc), (x_in + sgn * lp, zc), (x_in + sgn * lp, zc + lt), (x_in, zc + lt + lp)]
        for pts in (lower, upper):
            adds.append(prism_y(pts, BZ + 5, D - T))
    for pts in ([(D - T, zc - lt - lp), (D - T, zc), (D - T - lp, zc), (D - T - lp, zc - lt)],
                [(D - T, zc), (D - T - lp, zc), (D - T - lp, zc + lt), (D - T, zc + lt + lp)]):
        adds.append(prism_x(pts, T, W - T))
    # rod bosses (front half) and tubes (rear half): one column per rod, from the front
    # boss to the back wall, on a web down to the base / up to the top (no overhang)
    ys = Y_SPLIT
    rb = ROD_BOSS_D / 2
    for x, z in ROD_PTS:
        y0 = ys - ROD_BOSS_LEN
        adds.append(cyl_y(x, z, rb, y0, D - T + 0.1))
        if z < H / 2:
            adds.append(box(x - rb, y0, T - 0.1, x + rb, D - T + 0.1, z))
        else:
            adds.append(box(x - rb, y0, z, x + rb, D - T + 0.1, H - T + 0.1))
    # card-guide rails for the board
    xb = info["xb"]
    rx0, rx1 = xb - RAIL_CHEEK, xb + PCB_T + RAIL_CHEEK
    y_front = info["yb"] - PCB_L - 1.0
    rail_h = 19.0
    adds.append(box(rx0, y_front - 6, T - 0.1, rx1, D - T + 0.1, T + rail_h))            # bottom
    # top rail: hangs off the left wall at the board's top edge, with a 45-degree gusset
    # above it so the upside-down-printed upper quarters need no supports
    zt0, zt1 = info["z_bt"] - RAIL_DEPTH - 3.0, info["z_bt"] + 6.0
    adds.append(box(T - 0.1, y_front - 6, zt0, rx1, D - T + 0.1, zt1))
    adds.append(prism_y([(T - 0.1, zt1), (rx1, zt1), (T - 0.1, zt1 + (rx1 - T))], y_front - 6, D - T + 0.1))
    slot = (xb - 0.2, xb + PCB_T + 0.2)
    cuts.append(box(slot[0], y_front, info["z_bb"] - 0.3, slot[1], D - T, T + rail_h + 1))
    cuts.append(box(slot[0], y_front, zt0 - 1, slot[1], D - T, info["z_bt"] + 0.3))
    s = fuse([s] + adds)
    # seam bolts: inserts in the lower / front lip, clearance in the other one
    holes = []
    for y in spaced(BZ + 20, ys - 12, 50) + spaced(ys + 12, D - T - 20, 50):   # clear of the split
        for x in (T + 4.5, W - T - 4.5):
            holes.append(cyl_z(x, y, INSERT_D / 2, zc - INSERT_DEPTH, zc + 0.1))
            holes.append(cyl_z(x, y, CLEAR_D / 2, zc, zc + lt + lp + 2))
    for x in spaced(T + 20, W - T - 20, 55):
        y = D - T - 4.5
        holes.append(cyl_z(x, y, INSERT_D / 2, zc - INSERT_DEPTH, zc + 0.1))
        holes.append(cyl_z(x, y, CLEAR_D / 2, zc, zc + lt + lp + 2))
    cuts += holes
    HARDWARE["chin-line seam bolts M3x14 + heat-set inserts"] = len(holes) // 2
    # rods: insert in the front boss, bore through the rear tube and back wall, counterbore
    # for the washer and acorn nut on the back face
    for x, z in ROD_PTS:
        cuts.append(cyl_y(x, z, INSERT_D / 2, ys - INSERT_DEPTH - 1, ys + 0.1))
        cuts.append(cyl_y(x, z, ROD_BORE_D / 2, ys, D + 1))
        cuts.append(cyl_y(x, z, ROD_CBORE_D / 2, D - 1.0, D + 1))
    HARDWARE["join rods M3 x 180 mm (threaded rod) + washer + acorn nut + heat-set insert"] = len(ROD_PTS)
    # back panel: port cut-outs from the board model, with a 2 mm recess outside
    for sol in board.Solids:
        bb = sol.BoundBox
        if bb.YMax > info["yb"] - 3 and bb.XMin < xb - 0.5 and bb.XLength < 40:
            m = 1.0
            cuts.append(box(bb.XMin - m, D - T - 1, bb.ZMin - m, min(bb.XMax + m, xb), D + 1, bb.ZMax + m))
            cuts.append(box(bb.XMin - 3, D - 2.0, bb.ZMin - 3, min(bb.XMax + 3, xb + 3), D + 1, bb.ZMax + 3))
    # PS/2 (J1): its opening sits 4.2 mm in from the board edge, so the plug comes in
    # through the back panel; the opening and recess clear the plug's moulding
    (x0, x1, y0, y1), h = STAND_INS["J1"]
    yj, zj0 = pcb_to_case(info, x1, y1)
    _, zj1 = pcb_to_case(info, x0, y0)
    m = PS2_OPEN
    cuts.append(box(xb - h - m, D - T - BACK_GAP - 1, zj0 - m, xb, D + 1, zj1 + m))
    cuts.append(box(xb - h - 3, D - 2.0, zj0 - 3, xb + 3, D + 1, zj1 + 3))
    # VGA loop slot (a short VGA cable from J2 comes back in to the LCD driver board)
    _, zj2 = pcb_to_case(info, 0, 190.0)
    cuts.append(rbox_y(xb + 6, D - T - 1, zj2 - 7, xb + 40, D + 1, zj2 + 7, 6.9))
    cuts.append(cyl_y(DC_JACK_POS[0], DC_JACK_POS[1], DC_JACK_D / 2, D - T - 1, D + 1))
    # vents: base and top, toward the back
    for x in spaced(60, W - 60, 12):     # between the rod tubes
        cuts.append(rbox_x(x - 2, 215, -1, x + 2, 315, T + 1, 1.9) if False else
                    box(x - 2, 215, -1, x + 2, 315, T + 1))
        cuts.append(box(x - 2, 215, H - T - 1, x + 2, 315, H + 1))
    # rubber-foot pockets
    for x, y in ((25, BZ + 25), (W - 25, BZ + 25), (25, D - 25), (W - 25, D - 25)):
        cuts.append(cyl_z(x, y, 6.2, -1, 1.0))
    # driver-board tray posts (inserts) in the chin
    tx, ty = TRAY_POS
    tw, td = TRAY
    posts = [(tx + 6, ty + 6), (tx + tw - 6, ty + 6), (tx + 6, ty + td - 6), (tx + tw - 6, ty + td - 6)]
    s = fuse([s] + [cyl_z(x, y, 4.0, T - 0.1, T + TRAY_POST_H) for x, y in posts])
    cuts += [cyl_z(x, y, INSERT_D / 2, T + TRAY_POST_H - INSERT_DEPTH, T + TRAY_POST_H + 1) for x, y in posts]
    s = cut(s, cuts)
    # keep the case at least 1 mm clear of every component (lips and rails get cut back)
    pcb = pcb_body(board)
    keep_out = []
    for sol in board.Solids:
        bb = sol.BoundBox
        m = 0.3 if sol.isSame(pcb) else 1.0        # the bare board needs only a slot
        keep_out.append(box(bb.XMin - m, bb.YMin - m, bb.ZMin - m, bb.XMax + m, bb.YMax + m, bb.ZMax + m))
    s = cut(s, keep_out)
    s = door_opening(s, info)
    return s


# ---------------------------------------------------------------- controls door
def door_rect(info):
    y0, _ = pcb_to_case(info, DOOR_PX[1], 0)
    y1, _ = pcb_to_case(info, DOOR_PX[0], 0)
    _, z1 = pcb_to_case(info, 0, DOOR_PY[0])
    _, z0 = pcb_to_case(info, 0, DOOR_PY[1])
    return y0, y1, max(z0, T + 22.0), min(z1, H - T - 22.0)


def magnet_spots(r):
    y0, y1, z0, z1 = r
    yc = (y0 + y1) / 2
    return [(yc, z0 + DOOR_LEDGE / 2 + 1.5), (yc, z1 - DOOR_LEDGE / 2 - 1.5),
            (y0 + 1.5, (z0 + z1) / 2), (y1 - 1.5, (z0 + z1) / 2)]


def door_opening(s, info):
    y0, y1, z0, z1 = door_rect(info)
    lg = DOOR_LEDGE
    # clear everything in the opening (wall and seam lips), then add the ledge frame inside
    s = cut(s, [rbox_x(-1, y0, z0, T + LIP + 0.5, y1, z1, 3.0)])
    frame = cut(rbox_x(T - 0.01, y0 - 1, z0 - 1, T + DOOR_LEDGE_T, y1 + 1, z1 + 1, 3.0),
                [rbox_x(T - 1, y0 + lg, z0 + lg, T + DOOR_LEDGE_T + 1, y1 - lg, z1 - lg, 2.0)])
    s = fuse([s, frame])
    # magnet pockets in the ledge (from the outside face of the ledge)
    s = cut(s, [Part.makeCylinder(MAGNET_D / 2, MAGNET_H, V(T - 0.01, y, z), V(1, 0, 0))
                for y, z in magnet_spots((y0 + lg / 2, y1 - lg / 2, z0 + lg / 2, z1 - lg / 2))])
    return s


def door(info):
    y0, y1, z0, z1 = door_rect(info)
    c = 0.3
    d = rbox_x(0, y0 + c, z0 + c, T, y1 - c, z1 - c, 3.0)
    lg = DOOR_LEDGE
    mags = [Part.makeCylinder(MAGNET_D / 2, MAGNET_H, V(T - MAGNET_H + 0.01, y, z), V(1, 0, 0))
            for y, z in magnet_spots((y0 + lg / 2, y1 - lg / 2, z0 + lg / 2, z1 - lg / 2))]
    zc = (z0 + z1) / 2
    notch = cyl_x(y0 + c, zc, 9.0, -1, 1.6)            # finger notch on the front edge
    return cut(d, mags + [notch])


def tray():
    tx, ty = TRAY_POS
    tw, td = TRAY
    t = box(tx, ty, 0, tx + tw, ty + td, 3.0)
    holes = [cyl_z(x, y, CLEAR_D / 2, -1, 4) for x, y in
             [(tx + 6, ty + 6), (tx + tw - 6, ty + 6), (tx + 6, ty + td - 6), (tx + tw - 6, ty + td - 6)]]
    slots = [rbox_x(tx + 18, y - 1.7, -1, tx + tw - 18, y + 1.7, 4, 0) if False else
             box(tx + 18, y - 1.7, -1, tx + tw - 18, y + 1.7, 4)
             for y in spaced(ty + 14, ty + td - 14, 14)]
    t = cut(t, holes + slots)
    t.translate(V(0, 0, T + TRAY_POST_H))
    return t


# ---------------------------------------------------------------- split and check
def wall_band(i0, i1, y0, y1):
    """The part of the side / top / base walls between insets i0 and i1 from the outside."""
    return rbox_y(i0, y0, i0, W - i0, y1, H - i0, R - i0).cut(
        rbox_y(i1, y0 - 1, i1, W - i1, y1 + 1, H - i1, R - i1))


def quarters(s):
    """Split the shell at the chin line and at Y_SPLIT. The rear quarters keep a tongue of
    wall reaching forward into a rebate in the front quarters (a lap joint: the outside
    stays one surface, the inside lines up)."""
    big = 1000.0
    ys = Y_SPLIT
    i0, i1, tl = TONGUE
    gap = TONGUE_GAP
    tongue = s.common(wall_band(i0, i1, ys - tl, ys + 0.1))
    rebate = wall_band(i0 - gap, i1 + gap, ys - tl - gap, ys + 1)
    q = {}
    for zn, (za, zb) in (("lower", (-1, Z_CHIN)), ("upper", (Z_CHIN, H + 1))):
        zbox = box(-big, -big, za, big, big, zb)
        front = cut(s.common(box(-big, -1, za, big, ys, zb)), [rebate])
        rear = s.common(box(-big, ys, za, big, D + 1, zb))
        rear = fuse([rear, tongue.common(zbox)])
        q["shell_%s_front" % zn] = front
        q["shell_%s_rear" % zn] = rear
    return q


def ps2_plug(info):
    """A keyboard plug in J1: 13 mm round moulding, 25 mm of it, plus the cable."""
    (x0, x1, y0, y1), h = STAND_INS["J1"]
    yj, z0 = pcb_to_case(info, x0, y1)
    _, z1 = pcb_to_case(info, x0, y0)
    x, z = info["xb"] - h / 2, (z0 + z1) / 2
    return Part.makeCompound([cyl_y(x, z, 6.5, yj + 0.5, yj + 25), cyl_y(x, z, 2.5, yj + 25, D + 60)])


def rods():
    """The 4 join rods with their acorn nuts, as one reference model."""
    return Part.makeCompound([cyl_y(x, z, 1.5, Y_SPLIT - INSERT_DEPTH, D + 4) for x, z in ROD_PTS] +
                             [cyl_y(x, z, 3.0, D, D + 4) for x, z in ROD_PTS])


def main():
    os.makedirs(OUT, exist_ok=True)
    report = []
    progress = open(os.path.join(OUT, "progress.txt"), "w")

    def say(t):
        report.append(t)
        progress.write(t + "\n")
        progress.flush()
    board, info = load_board()
    g = panel_geometry()
    say("board: tallest part %.1f mm above the PCB; component face at X = %.1f mm; "
        "board X %.1f-%.1f, Y %.1f-%.1f, Z %.1f-%.1f" %
        (info["zmax"] - PCB_T, info["xb"], board.BoundBox.XMin, board.BoundBox.XMax,
         board.BoundBox.YMin, board.BoundBox.YMax, board.BoundBox.ZMin, board.BoundBox.ZMax))
    panel = panel_model(g)
    upper_bezel, chin = bezel_parts(g)
    frame = clamp_frame(g)
    sh = shell(info, g, board)
    parts = dict(quarters(sh))
    parts.update(bezel_upper=upper_bezel, bezel_chin=chin, panel_clamp=frame,
                 controls_door=door(info), driver_tray=tray())
    refs = dict(ref_board=board, ref_lcd_panel=panel, ref_rods=rods(), ref_ps2_plug=ps2_plug(info))

    say("\nprinted parts (size X x Y x Z, mm):")
    ok = True
    for name, p in parts.items():
        bb = p.BoundBox
        dims = sorted([bb.XLength, bb.YLength, bb.ZLength])
        fits = dims[0] <= BED and dims[1] <= BED and dims[2] <= BED and sorted(dims)[1] <= BED
        ok &= fits
        say("  %-20s %6.1f x %6.1f x %6.1f  %s  %d solid(s)" %
            (name, bb.XLength, bb.YLength, bb.ZLength, "fits" if fits else "TOO BIG", len(p.Solids)))
    say("all parts fit a %.0f mm bed: %s" % (BED, ok))

    say("\nfit check (overlap volume, mm^3; must be 0):")
    for rname, r in refs.items():
        for name, p in parts.items():
            if not r.BoundBox.intersect(p.BoundBox):
                continue
            v = sum(r_s.common(p).Volume for r_s in check_solids(r) if r_s.BoundBox.intersect(p.BoundBox))
            say("  %-14s vs %-20s %10.3f" % (rname, name, v))
    shells = [n for n in parts if n.startswith("shell_")]
    for i, a in enumerate(shells):          # the tongue must sit in its rebate, not in it
        for b in shells[i + 1:]:
            if parts[a].BoundBox.intersect(parts[b].BoundBox):
                say("  %-14s vs %-20s %10.3f" % (a, b, parts[a].common(parts[b]).Volume))
    HARDWARE["bezel screws M3x10 + heat-set inserts"] = len(front_lip_screws())
    HARDWARE["panel clamp screws M3x8 + heat-set inserts"] = 4
    HARDWARE["driver tray screws M3x8 + heat-set inserts"] = 4
    HARDWARE["door magnets 6x3 mm (4 in the door, 4 in the ledge)"] = 8
    HARDWARE["rubber feet, 12 mm"] = 4
    say("\nhardware:")
    for k, n in HARDWARE.items():
        say("  %3d  %s" % (n, k))
    say("\nboard gap to the left wall: %.1f mm (tallest part)" % (board.BoundBox.XMin - T))

    # outputs
    import MeshPart
    for name, p in parts.items():   # 0.1 mm chord error, 20-degree arc steps: print quality
        mesh = MeshPart.meshFromShape(Shape=p, LinearDeflection=0.1, AngularDeflection=0.35)
        mesh.write(os.path.join(OUT, name + ".stl"))
    doc = FreeCAD.newDocument("Open8VGA_Enclosure")
    for name, p in list(parts.items()) + list(refs.items()):
        o = doc.addObject("Part::Feature", name)
        o.Shape = p
    doc.recompute()
    doc.saveAs(os.path.join(OUT, "open8-vga-enclosure.FCStd"))
    Part.makeCompound(list(parts.values()) + [panel]).exportStep(os.path.join(OUT, "open8-vga-enclosure.step"))
    with open(os.path.join(OUT, "fit_report.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    say("wrote " + OUT)


main()
