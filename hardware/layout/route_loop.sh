#!/bin/zsh
# Route the KiCad board with Freerouting one pass at a time (Freerouting 2.5's native CLI
# crashes when it snapshots the board between passes, so each run does exactly one pass).
# Each step: DSN (with the copper so far) -> dsn_fix -> one Freerouting pass -> SES -> board.
# Stops when nothing is left unrouted, two passes in a row gain nothing, or a pass
# runs past 30 minutes (Freerouting can oscillate on dense buses).
# usage: route_loop.sh <first-step-number> <first-raw-dsn> [plane layers hidden from the router]
# Author: Adham Elshafei
set -u
ROOT=${0:A:h}/../..
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
FR=$ROOT/tools/freerouting/cli/freerouting-cli
BOARD=$ROOT/kicad/board/open8-vga-motherboard.kicad_pcb
DIR=$ROOT/build/route
step=$1
raw=$2
planes=${3:-In1.Cu,In4.Cu}
last=999999
stuck=0
while true; do
  python3 $ROOT/hardware/layout/dsn_fix.py $raw $DIR/step$step.dsn $planes || exit 1
  $FR -de $DIR/step$step.dsn -do $DIR/step$step.ses -mp 1 -mt 8 > $DIR/freerouting$step.log 2>&1 &
  pid=$!
  for i in {1..1800}; do kill -0 $pid 2>/dev/null || break; sleep 1; done
  kill -0 $pid 2>/dev/null && { kill $pid; echo "step $step: pass hung for 30 min, stopped"; exit 2; }
  left=$(grep -o '([0-9]* unrouted' $DIR/freerouting$step.log | tail -1 | tr -dc 0-9)
  echo "step $step: ${left:-?} unrouted"
  [[ -f $DIR/step$step.ses ]] || { echo "no session written"; exit 1; }
  next=$((step + 1))
  $KP $ROOT/hardware/layout/ses_step.py $BOARD $DIR/step$step.ses $DIR/step${next}_raw.dsn 2>&1 | grep -v -e swig -e assert
  [[ ${left:-1} -eq 0 ]] && { echo "fully routed"; exit 0; }
  if (( left >= last )); then stuck=$((stuck + 1)); else stuck=0; fi
  (( stuck >= 2 )) && { echo "no progress for 2 passes; stopping at $left"; exit 0; }
  last=$left
  step=$next
  raw=$DIR/step${step}_raw.dsn
done
