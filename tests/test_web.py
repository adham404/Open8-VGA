"""The browser emulator core (tools/web/open8core.js) must match the Python simulator
exactly: same firmware, same scripted keys, identical full-state hash after every chunk."""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import build_web   # noqa: E402
import fwsim       # noqa: E402
import ps2         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK = 50000


def state_hash(s):
    h = 0x811c9dc5

    def mix(v):
        nonlocal h
        h = ((h ^ (v & 0xFF)) * 0x01000193) & 0xFFFFFFFF
    c, m = s.cpu, s.m
    for v in (c.a, c.b, c.x & 0xFF, c.x >> 8, c.sp, c.pc & 0xFF, c.pc >> 8, c.flags,
              1 if c.halted else 0, m.bank, m.scroll_x, m.scroll_y, 1 if m.trap else 0,
              1 if m.violation else 0):
        mix(v)
    for arr in (m.sram, m.vram, m.font):
        for v in arr:
            mix(v)
    if m.eeprom is not None:
        for v in m.eeprom.mem:
            mix(v)
    return h


def scenario():
    """Boot, open the editor, load Tetris (F5 7 Y), assemble+run (F3), then play."""
    keys = {8: " ", 14: ["F5"], 20: "7", 26: "y", 32: ["F3"]}
    play = ["LEFT", "LEFT", "UP", " ", "RIGHT", "UP", "UP", " ", "DOWN", "DOWN", " ", "ESC"]
    for i, k in enumerate(play):
        keys[470 + 12 * i] = [k] if k.isupper() else k
    # back in the editor: save Tetris to slot 2, start a new program, load slot 2 again
    timeline = [(624, " "), (640, ["F4"]), (660, "2"),            # saving takes ~330 chunks
                (1000, ["F9"]), (1010, "y"), (1020, ["F6"]), (1040, "2"), (1060, "y")]
    keys.update(dict(timeline))
    t = 1220
    actions = {}
    for chunk, k in keys.items():
        actions[chunk] = ps2.press(k[0]) if isinstance(k, list) else ps2.text_to_scancodes(k)
    return actions, t + 200


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TestWebEmulator(unittest.TestCase):
    def test_js_core_matches_python_simulator(self):
        flash, _ = fwsim.firmware()
        actions, chunks = scenario()
        s = fwsim.boot()
        s.m.font[:] = bytes(4096)          # font RAM starts empty; the firmware loads it
        py = []
        for i in range(chunks):
            if i in actions:
                s.kb.type_bytes(actions[i], s.m.now)
            s.run(CHUNK)
            py.append([s.m.now, state_hash(s)])
        self.assertIn("Loaded 12", s.text_row(28))                        # saved, cleared, loaded
        self.assertGreater(s.m.eeprom.writes, 90)
        sc = {"flash": base64.b64encode(flash).decode(), "isa": build_web.isa_table(),
              "cycles": base64.b64encode(build_web.cycle_bytes()).decode(),
              "chunk": CHUNK, "chunks": chunks,
              "actions": {str(k): v for k, v in actions.items()}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(sc, f)
        try:
            out = subprocess.run(["node", os.path.join(HERE, "web_harness.js"), f.name],
                                 capture_output=True, text=True, check=True).stdout
        finally:
            os.unlink(f.name)
        js = json.loads(out)
        first = next((i for i, (a, b) in enumerate(zip(py, js)) if a != b), None)
        self.assertIsNone(first, "diverged at chunk %s: py %s js %s" % (
            first, py[first] if first is not None else "", js[first] if first is not None else ""))
        self.assertEqual(len(js), chunks)


if __name__ == "__main__":
    unittest.main()
