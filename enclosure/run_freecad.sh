#!/bin/sh
# Run a script in FreeCAD's command-line interpreter. FreeCAD swallows the script's own
# output, so scripts here log to files; any uncaught error goes to enclosure/out/error.txt.
# usage: enclosure/run_freecad.sh enclosure/build_enclosure.py
# Author: Adham Elshafei
set -e
FC=${FREECADCMD:-/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd}
SCRIPT=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
OUT=$(dirname "$SCRIPT")/out
mkdir -p "$OUT"
rm -f "$OUT/error.txt"
"$FC" -c "
import traceback
try:
    exec(open('$SCRIPT').read(), {'__file__': '$SCRIPT', '__name__': '__main__'})
except BaseException:
    open('$OUT/error.txt', 'w').write(traceback.format_exc())
" > "$OUT/freecad_console.txt" 2>&1
if [ -f "$OUT/error.txt" ]; then cat "$OUT/error.txt"; exit 1; fi
