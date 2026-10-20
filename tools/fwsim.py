"""Helpers to boot and drive the firmware in the simulator (used by tests and screenshots)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_firmware   # noqa: E402
import system           # noqa: E402

_FLASH = {}


def firmware():
    if "img" not in _FLASH:
        flash, a, stats = build_firmware.build()
        _FLASH["img"], _FLASH["asm"], _FLASH["stats"] = flash, a, stats
    return _FLASH["img"], _FLASH["asm"]


def boot(fast=True):
    flash, a = firmware()
    s = system.System(flash, fast=fast)
    s.cpu.pc = 0
    s.cpu.sp = 0
    s.sym = a.symbols
    return s


def wait_idle(s, label="ED_WAIT", max_cycles=40_000_000):
    """Run until the firmware is waiting for a key at `label` (default: editor loop)."""
    target = s.sym[label]
    return s.run_until(target, max_cycles=max_cycles)


def press(s, text=None, keys=(), label="ED_WAIT", max_cycles=60_000_000):
    """Type keys one at a time (like a person), each time running until the firmware
    is idle again at `label`."""
    items = [(ch, ()) for ch in (text or "")] + [(None, (k,)) for k in keys]
    if not items:                       # just let already-queued keys be processed
        items = [(None, ())]
    for ch, k in items:
        if not _press_one(s, ch, k, label, max_cycles):
            return False
    return True


def _press_one(s, text, keys, label, max_cycles):
    s.type(text, keys)
    s.run(20000)
    # let all typed bytes be processed: idle at label with nothing pending
    for _ in range(4000):
        if not wait_idle(s, label, max_cycles):
            return False
        if not s.kb.buffer and s.kb.frame is None and not s.rx.ready:
            return True
        s.run(5000)
    return False


def screen_text(s):
    return [s.text_row(r) for r in range(30)]


def call(s, label, regs=None, max_cycles=200_000_000):
    """Call a firmware routine directly; returns when it RETurns (to test_halt)."""
    ret = s.sym["TEST_HALT"]
    s.m.sram[0xAFFE - 0x8000] = ret & 0xFF
    s.m.sram[0xAFFF - 0x8000] = ret >> 8
    s.cpu.sp = 0xFE
    s.cpu.pc = s.sym[label]
    s.cpu.halted = False
    for k, v in (regs or {}).items():
        setattr(s.cpu, k, v)
    return s.run_until_halt(max_cycles)


def assemble_onboard(source, s=None):
    """Run the ROM assembler on `source`. Returns (ok, bytes or (err, line), system)."""
    s = s or boot()
    data = source.encode("latin-1") + b"\0"
    assert len(data) < 0x4000
    for i, b in enumerate(data):
        s.m.sram[0xB000 - 0x8000 + i] = b
    for i in range(0x8000 - 0x8000, 0x2F00):
        s.m.sram[i] = 0xEE
    if not call(s, "ASM_MAIN"):
        raise RuntimeError("assembler did not return")
    ram = lambda a: s.m.sram[a - 0x8000]
    if s.cpu.flags & 1:
        line = ram(0xFC63) | ram(0xFC64) << 8
        return False, (ram(0xFC69), line), s
    end = ram(0xFC61) | ram(0xFC62) << 8
    return True, bytes(ram(a) for a in range(0x8000, end)), s
