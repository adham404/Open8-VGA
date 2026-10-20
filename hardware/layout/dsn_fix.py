"""Prepare a KiCad-exported Specctra DSN for Freerouting.

* Sets the routing rules (pcbnew's script export ignores the project's net classes):
  signals 0.2 mm / 0.15 mm, VCC and GND 0.5 mm, VBUS 1 mm.
* Hides the plane layers and the VCC/GND nets from the router: In1.Cu becomes the GND
  plane and In4.Cu the VCC plane after routing (signals use F, In2, In3, B), and every through-hole power pin connects
  to its plane directly. (Freerouting 2.5's native CLI cannot handle declared planes.)
* Adds a via-to-via clearance that keeps JLCPCB's 0.5 mm hole-to-hole rule.
* Removes the footprint outline drawings (they play no part in routing, and Freerouting
  2.5's native CLI cannot snapshot them).

Environment: DSN_DEFAULT_RULE="width,clearance" in um overrides the signal rule (default 200,150).

usage: dsn_fix.py <in.dsn> <out.dsn> [plane layers, comma-separated; default In1.Cu,In4.Cu]
Author: Adham Elshafei
"""
import os
import re
import sys

CLASS_RULES = {"PWR_VCC": (500, 150), "GND": (500, 150)}
DEFAULT = tuple(int(v) for v in os.environ.get("DSN_DEFAULT_RULE", "200,150").split(","))
PLANE_LAYERS = ("In1.Cu", "In4.Cu")       # 6 layers: In1 = GND plane, In4 = VCC plane
PLANE_NETS = ("GND", "VCC")


def strip_forms(s, head):
    """Remove every balanced '(head ...)' form."""
    out, i = [], 0
    while True:
        j = s.find("(" + head, i)
        if j < 0:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:j])
        depth, k = 0, j
        while True:
            if s[k] == "(":
                depth += 1
            elif s[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1


def main(src, dst, plane_layers=PLANE_LAYERS):
    s = open(src).read()
    s = strip_forms(s, "outline ")
    # board-wide rule
    s = re.sub(r"\(rule\s*\(width [\d.]+\)\s*\(clearance [\d.]+\)",
               "(rule\n      (width %d)\n      (clearance %d)" % DEFAULT, s, count=1)
    # per-class rules
    out, i = [], 0
    while True:
        j = s.find("(class ", i)
        if j < 0:
            out.append(s[i:])
            break
        k, depth = j, 0
        while True:
            if s[k] == "(":
                depth += 1
            elif s[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = s[j:k + 1]
        name = body.split()[1]
        w, c = CLASS_RULES.get(name, DEFAULT)
        if name == "kicad_default":
            head, rest = body.split("(circuit", 1)
            body = re.sub(r"(?<=\s)VBUS(?=\s)", " ", head) + "(circuit" + rest
        body = re.sub(r"\(width [\d.]+\)\s*\(clearance [\d.]+\)",
                      "(width %d)\n        (clearance %d)" % (w, c), body)
        out.append(s[i:j] + body)
        i = k + 1
    s = "".join(out)
    # inner layers become the GND and VCC planes after routing (poured in KiCad), so the
    # router sees a 2-layer board and does not route VCC or GND at all
    for layer in plane_layers:
        s = strip_forms(s, "layer %s\n" % layer)
        s = re.sub(r"\s*\(shape \(\w+ %s [^()]*(\([^()]*\)[^()]*)*\)\)" % re.escape(layer), "", s)
    for net in PLANE_NETS:
        s = strip_forms(s, "net %s\n" % net)
        s = strip_forms(s, "class %s " % {"GND": "GND", "VCC": "PWR_VCC"}[net])
    # JLCPCB hole-to-hole 0.5 mm: 0.3 mm drills on 0.45 mm vias need 0.35 mm copper gap
    s = s.replace("(clearance 31.75 (type smd_smd))",
                  "(clearance 31.75 (type smd_smd))\n      (clearance 350 (type via_via))", 1)
    via = re.search(r'\(via "([^"]+)"\)', s).group(1)
    vbus = ('    (class PWR_IN VBUS\n      (circuit\n        (use_via "%s")\n' % via +
            '      )\n      (rule\n        (width 1000)\n        (clearance 150)\n      )\n    )\n')
    k = s.index("    (class kicad_default")
    s = s[:k] + vbus + s[k:]
    open(dst, "w").write(s)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *([sys.argv[3].split(",")] if len(sys.argv) > 3 else []))
