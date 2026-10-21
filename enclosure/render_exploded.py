"""Render an exploded view of the enclosure (FreeCAD GUI; the document is not saved).

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD enclosure/render_exploded.py

Author: Adham Elshafei
"""
import os

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore, QtGui

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    os.path.expanduser("~/Documents/Open8-VGA/enclosure")
OUT = os.path.join(HERE, "out", "img")
log = open(os.path.join(HERE, "out", "render_log.txt"), "w")

# how far each part moves out (X, Y, Z mm): the front half (with the screen parts further
# forward), the rear half with the board and door pulled out to the left, the rods behind
FRONT, REAR = -90, 90
OFFSETS = {
    "shell_lower_front": (0, FRONT, 0), "shell_upper_front": (0, FRONT, 40),
    "driver_tray": (0, FRONT, 0),
    "bezel_upper": (0, FRONT - 140, 40), "bezel_chin": (0, FRONT - 140, 0),
    "panel_clamp": (0, FRONT - 60, 40), "ref_lcd_panel": (0, FRONT - 100, 40),
    "shell_lower_rear": (0, REAR, 0), "shell_upper_rear": (0, REAR, 40),
    "ref_board": (-150, 0, 20), "controls_door": (-110, REAR, 20),
    "ref_rods": (0, REAR + 220, 20), "ref_ps2_plug": (-150, 60, 20),
    "ref_keypad": (0, REAR, 110),           # lifted out of its holder
}


def run():
    try:
        doc = FreeCAD.openDocument(os.path.join(HERE, "out", "open8-vga-enclosure.FCStd"))
        for o in doc.Objects:
            dx, dy, dz = OFFSETS.get(o.Name, (0, 0, 0))
            o.Placement.Base = FreeCAD.Vector(dx, dy, dz)
            o.ViewObject.Visibility = True
        view = Gui.activeDocument().activeView()
        view.setAnimationEnabled(False)
        view.viewIsometric()
        d = FreeCAD.Vector(1.0, 1.25, -0.6).normalize()
        u = FreeCAD.Vector(0, 0, 1)
        r = d.cross(u).normalize()
        u2 = r.cross(d).normalize()
        m = FreeCAD.Matrix(r.x, u2.x, -d.x, 0, r.y, u2.y, -d.y, 0, r.z, u2.z, -d.z, 0, 0, 0, 0, 1)
        view.setCameraOrientation(FreeCAD.Placement(m).Rotation)
        view.fitAll()
        Gui.updateGui()
        path = os.path.join(OUT, "exploded.png")
        view.saveImage(path, 1800, 1500, "White")
        log.write("wrote %s\n" % path)
        FreeCAD.closeDocument(doc.Name)
    except Exception:
        import traceback
        log.write(traceback.format_exc())
    log.close()
    QtGui.QApplication.instance().quit()


QtCore.QTimer.singleShot(1500, run)
