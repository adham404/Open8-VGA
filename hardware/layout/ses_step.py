"""Import a Freerouting session into the KiCad board, save it, and export a fresh DSN that
carries the routed copper (for the next pass). Run with KiCad's bundled Python.

usage: ses_step.py <board.kicad_pcb> <in.ses> <out.dsn>
Author: Adham Elshafei
"""
import sys

import pcbnew


def main(board_path, ses, dsn):
    b = pcbnew.LoadBoard(board_path)
    if not pcbnew.ImportSpecctraSES(b, ses):
        raise SystemExit("SES import failed")
    b.Save(board_path)
    tracks = list(b.Tracks())
    vias = sum(1 for t in tracks if t.Type() == pcbnew.PCB_VIA_T)
    print("board now has %d track segments and %d vias" % (len(tracks) - vias, vias))
    if not pcbnew.ExportSpecctraDSN(b, dsn):
        raise SystemExit("DSN export failed")


if __name__ == "__main__":
    main(*sys.argv[1:4])
