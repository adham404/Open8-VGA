"""Render preview images of the enclosure (needs the FreeCAD GUI; it opens a window briefly).

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD enclosure/render_views.py

Reads enclosure/out/open8-vga-enclosure.FCStd, writes PNGs to enclosure/out/img/, then
saves the document with colours and a fitted isometric view (a file saved by the
command-line build has no view state, so it would open with nothing in frame).
Author: Adham Elshafei
"""
import os

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore, QtGui

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    os.path.expanduser("~/Documents/Open8-VGA/enclosure")
OUT = os.path.join(HERE, "out", "img")
os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(HERE, "out", "render_log.txt"), "w")

PLATINUM = (0.90, 0.88, 0.82)
COLORS = {"ref_board": (0.10, 0.42, 0.20), "ref_lcd_panel": (0.06, 0.07, 0.08),
          "controls_door": (0.86, 0.83, 0.76), "panel_clamp": (0.35, 0.35, 0.38),
          "driver_tray": (0.35, 0.35, 0.38), "ref_rods": (0.55, 0.56, 0.60)}


def setup():
    doc = FreeCAD.openDocument(os.path.join(HERE, "out", "open8-vga-enclosure.FCStd"))
    Gui.activeDocument().activeView().setAnimationEnabled(False)
    for o in doc.Objects:
        vo = o.ViewObject
        vo.ShapeColor = COLORS.get(o.Name, PLATINUM)
        vo.LineColor = (0.45, 0.43, 0.40)
        vo.LineWidth = 1.0
    return doc


def show(doc, hidden=()):
    for o in doc.Objects:
        o.ViewObject.Visibility = o.Name not in hidden


def shot(name, direction, up=(0, 0, 1), hidden=()):
    doc = FreeCAD.ActiveDocument
    show(doc, hidden)
    view = Gui.activeDocument().activeView()
    view.viewIsometric()
    # point the camera along `direction` with Z up
    d = FreeCAD.Vector(*direction).normalize()
    u = FreeCAD.Vector(*up)
    right = d.cross(u).normalize()
    up2 = right.cross(d).normalize()
    m = FreeCAD.Matrix(right.x, up2.x, -d.x, 0, right.y, up2.y, -d.y, 0, right.z, up2.z, -d.z, 0, 0, 0, 0, 1)
    view.setCameraOrientation(FreeCAD.Placement(m).Rotation)
    view.fitAll()
    Gui.updateGui()
    path = os.path.join(OUT, name + ".png")
    view.saveImage(path, 1600, 1200, "White")
    log.write("wrote %s\n" % path)
    log.flush()


def run():
    try:
        doc = setup()
        inside = ("shell_upper_front", "shell_upper_rear", "bezel_upper", "bezel_chin")
        shot("front_left", (1.0, 1.2, -0.55))                       # looking from front-left
        shot("rear_left", (1.0, -1.1, -0.45))                       # back panel and door side
        shot("rear_right", (-1.0, -1.1, -0.45))
        shot("front", (0, 1, 0))
        shot("left_door_off", (1.0, -0.6, -0.35), hidden=("controls_door",))
        shot("inside_top_off", (0.8, 0.9, -1.0), hidden=inside)
        shot("parts_print", (0.9, 1.1, -0.7),
             hidden=("ref_board", "ref_lcd_panel"))
        # leave the document opening nicely in the GUI: everything shown, isometric, fitted
        show(doc)
        view = Gui.activeDocument().activeView()
        view.viewIsometric()
        view.fitAll()
        Gui.updateGui()
        doc.save()
        log.write("saved the document with its view state\n")
    except Exception:
        import traceback
        log.write(traceback.format_exc())
    log.close()
    QtGui.QApplication.instance().quit()


QtCore.QTimer.singleShot(1500, run)
