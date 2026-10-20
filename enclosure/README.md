# Open8-VGA enclosure

A compact-Macintosh-style case for the Rev A board and an 8" LCD, designed in FreeCAD.

![Front-left view](out/img/front_left.png)

Author: Adham Elshafei. **Status: designed and fit-checked in CAD only; not yet printed.**

## What it is

| | |
|---|---|
| Outside size | 250 W × 340 H × 345 D mm |
| Screen | 8" 800 × 600, 4:3 (see below), behind a recessed bezel |
| Board | stands upright on the left wall, components facing out, held top and bottom in printed card-guide rails (Rev A has no mounting holes) |
| Controls | a removable magnetic door in the left wall opens onto the board's control strip: RESET, STEP, CONTINUE, both slide switches, all jumpers, the slow-clock trimmer, the PWR/HALT LEDs and the logic-analyser and expansion headers |
| Ports | back panel: VGA, USB-C power and PS/2 cut-outs (measured from the board model), a slot for the VGA loop cable, a 12 V jack for the display; keyboard extension socket on the right wall |
| Printing | 9 parts, every one fits a 256 × 256 × 256 mm bed, none needs supports |

| Inside | Back (ports) | Controls door off |
|---|---|---|
| ![](out/img/inside_top_off.png) | ![](out/img/rear_left.png) | ![](out/img/left_door_off.png) |

## Files

| File | |
|---|---|
| `build_enclosure.py` | the parametric model: every dimension is a named setting at the top |
| `out/*.stl` | the 9 printable parts |
| `out/open8-vga-enclosure.FCStd` | FreeCAD document: all parts plus the board and the LCD as reference models |
| `out/open8-vga-enclosure.step` | the case and panel as STEP, for other CAD tools |
| `out/fit_report.txt` | part sizes, overlap check, hardware counts |
| `render_views.py` | renders `out/img/` (opens the FreeCAD window briefly) |

Regenerate (FreeCAD 1.1 at `/Applications/FreeCAD.app`, KiCad 10):

```sh
kicad-cli pcb export step --subst-models -o build/enclosure/open8-vga-board.step kicad/board/open8-vga-motherboard.kicad_pcb
enclosure/run_freecad.sh enclosure/build_enclosure.py
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD enclosure/render_views.py
```

The build places the real board model (every component, from KiCad) and the LCD in the
case and checks that nothing overlaps: the last run reports 0.000 mm³ for every pair. The
case keeps at least 1 mm from every component automatically, so the seam lips and rails
are notched wherever a tall part needs room.

## The LCD panel

**8" 800 × 600 TFT, Innolux AT080TN52-class**, sold as a kit with a VGA/HDMI driver board
(for example BuyDisplay's 8" 800 × 600 kit with VGA, HDMI and AV inputs, about US$47 with a
12 V adapter; similar kits are on AliExpress).

* Outline 183.0 × 141.0 × 5.6 mm, active area 162.0 × 121.5 mm, 4:3.
* Why: it is the commonly available 4:3 8" panel that ships with a VGA driver board.
  Native 640 × 480 LED-backlit panels exist (Mitsubishi AA084VJ11 class) but are hard to
  source; this one scales 640 × 480 by 1.25×, so text is slightly soft.
* **Before printing, check your panel's drawing** against `PANEL_*` and `ACTIVE_*` in
  the script, especially `ACTIVE_DX` / `ACTIVE_DZ` (where the visible area sits inside
  the outline; the model assumes centred) and which edge the flex cable leaves from
  (`FPC_NOTCH_W`, at the bottom).

## Shopping list

| Qty | Part |
|---|---|
| 1 | 8" 800 × 600 LCD kit with a VGA driver board and 12 V adapter (above) |
| 1 | VGA cable, male–male, about 30 cm, ideally with one right-angle plug |
| 1 | panel-mount 5.5 × 2.1 mm DC jack (11 mm hole) for the display's 12 V |
| 1 | PS/2 extension, mini-DIN 6 female panel-mount to male, about 30 cm (check its hole: 15 mm with ears at ±13.5 mm assumed) |
| 58 | M3 brass heat-set inserts, 5 mm long, for 4.0 mm holes |
| 14 | M3 × 14 bolts (chin-line seam) |
| 36 | M3 × 10 bolts (mid-depth seam 18, bezel 18) |
| 8 | M3 × 8 bolts (panel clamp 4, driver tray 4) |
| 8 | neodymium magnets 6 × 3 mm (door) |
| 4 | rubber feet, 12 mm |
| | thin foam tape (0.5 mm) to cushion the LCD glass in the bezel |

## Printing

* PETG or ASA (the inside runs warm: about 5 W of logic plus the backlight; PLA can creep).
* 0.2 mm layers, 4 perimeters, 15–20 % infill. The walls are 3.5 mm, so the case is about
  2,500 cm³ of plastic, **roughly 3 kg of filament**. `T` (wall thickness) at 2.5 mm brings
  it to about 2.2 kg, at some cost in stiffness.
* Orientation: lower shell quarters upright (base on the bed); upper quarters upside down
  (top on the bed); bezel parts face-down; door, clamp and tray flat. Every overhang is
  45° or less.

## Assembly

1. Press the heat-set inserts in with a soldering iron: seam lips (lower and front
   quarters), the bezel rim and clamp bosses, the driver-tray posts.
2. Glue the magnets into the door ledge and the door (check the polarity first).
3. Bolt the two lower quarters together (mid-depth seam, M3 × 10), then the two upper
   quarters.
4. Slide the board into the bottom rail, connectors through the back panel.
5. Lower the upper assembly on, guiding the board's top edge into the top rail; bolt the
   chin-line seam (M3 × 14) from inside through the open front.
6. LCD: foam tape on the bezel pocket, panel in, clamp frame on (M3 × 8). Driver board on
   the tray (slots fit most hole patterns), tray onto its posts (M3 × 8).
7. VGA: from J2 out of the back panel, back in through the loop slot, to the driver
   board. 12 V jack to the driver board. PS/2 extension from J1 round to the right-wall
   socket.
8. Bezel and chin onto the front lip (M3 × 10, from inside), door on, feet on.

## To check on real parts

* The LCD drawing (above) and the driver board's size (the tray takes up to about
  110 × 90 mm).
* The panel-mount PS/2 socket's hole and ear spacing.
* The 3D models for the PS/2 jack (J1) and trimmer (RV1) are stand-in boxes; KiCad has no
  model for them. Leave a little extra room around them, or measure the real parts.
* Print one chin-line seam corner and the door first, to check insert holes and fits on
  your printer before committing 3 kg of filament.
