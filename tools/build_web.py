"""Build web/open8-vga.html: the browser emulator with the real firmware image embedded.

    python3 tools/build_web.py          Author: Adham Elshafei
"""
import base64
import datetime
import hashlib
import json
import os
import sys

import build_firmware
import isa
import microcode
import ps2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def isa_table():
    t = [None] * 256
    for ins in isa.INSTRS:
        ops = list(ins.operands) + [None, None]
        t[ins.opcode] = [ins.mnem, ops[0], ops[1]]
    return t


def cycle_bytes():
    return bytes(len(microcode.sequence(op, f)) for op in range(256) for f in range(16))


def keymap():
    """KeyboardEvent.code -> [extended, scan code set 2]."""
    km = {}
    for ch, code in ps2.KEYS.items():
        if ch.isalpha():
            km["Key" + ch.upper()] = [0, code]
        elif ch.isdigit():
            km["Digit" + ch] = [0, code]
    named = {"`": "Backquote", "-": "Minus", "=": "Equal", "\\": "Backslash", "[": "BracketLeft",
             "]": "BracketRight", ";": "Semicolon", "'": "Quote", ",": "Comma", ".": "Period",
             "/": "Slash", " ": "Space", "\n": "Enter", "\t": "Tab", "\b": "Backspace"}
    for ch, name in named.items():
        km[name] = [0, ps2.KEYS[ch]]
    special = {"ESC": "Escape", "LSHIFT": "ShiftLeft", "RSHIFT": "ShiftRight",
               "LCTRL": "ControlLeft", "LALT": "AltLeft", "CAPS": "CapsLock"}
    for name, code in ps2.SPECIAL.items():
        km[special.get(name, name)] = [0, code]
    ext = {"UP": "ArrowUp", "DOWN": "ArrowDown", "LEFT": "ArrowLeft", "RIGHT": "ArrowRight",
           "HOME": "Home", "END": "End", "PGUP": "PageUp", "PGDN": "PageDown",
           "INSERT": "Insert", "DELETE": "Delete", "RCTRL": "ControlRight", "RALT": "AltRight"}
    for name, code in ps2.EXTENDED.items():
        km[ext[name]] = [1, code]
    km["NumpadEnter"] = [1, 0x5A]
    return km


def build(out=None):
    flash, _, _ = build_firmware.build()
    core = open(os.path.join(WEB, "open8core.js")).read()
    page = open(os.path.join(WEB, "page.html")).read()
    stamp = hashlib.sha1(flash).hexdigest()[:8] + " · " + datetime.date.today().isoformat()
    html = (page.replace("{{CORE}}", core)
                .replace("{{FIRMWARE_B64}}", base64.b64encode(flash).decode())
                .replace("{{ISA_JSON}}", json.dumps(isa_table()))
                .replace("{{CYCLES_B64}}", base64.b64encode(cycle_bytes()).decode())
                .replace("{{KEYMAP_JSON}}", json.dumps(keymap()))
                .replace("{{BUILD}}", stamp))
    out = out or os.path.join(ROOT, "web", "open8-vga.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(html)
    return out, len(html)


if __name__ == "__main__":
    path, size = build(sys.argv[1] if len(sys.argv) > 1 else None)
    print("wrote %s (%d KB)" % (path, size // 1024))
