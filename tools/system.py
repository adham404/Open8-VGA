"""Whole-machine simulation: microcode CPU + video timing + PS/2 keyboard on one clock.

One CPU cycle == one character period (CHAR CLK = 25.175 MHz / 8), exactly as in hardware.
"""
import asm
import eeprom
import font
import ps2
import sim
import video


_CYCLES = None


def cycle_table():
    """Cycles per (opcode, flags) from the microcode, for the fast instruction-level CPU."""
    global _CYCLES
    if _CYCLES is None:
        import microcode
        _CYCLES = [[len(microcode.sequence(op, f)) for f in range(16)] for op in range(256)]
    return _CYCLES


class System:
    """fast=True uses the instruction-level RefCPU (about 3x faster) with cycle counts taken
    from the microcode; fast=False runs the microcode-level CPU cycle by cycle."""

    def __init__(self, flash=None, fast=False):
        self.m = sim.Machine(flash)
        self.m.font[:] = font.build_font()
        self.fast = fast
        self.cpu = sim.RefCPU(self.m) if fast else sim.MicroCPU(self.m)
        self.rx = ps2.Receiver()
        self.kb = ps2.Keyboard(self.rx)
        self.m.ps2, self.m.keyboard = self.rx, self.kb
        self.m.eeprom = eeprom.EEPROM25LC512()      # fitted in socket U_EE
        self.frame_pos = 0
        self.frames = 0

    def load_user_program(self, source):
        image, a = asm.assemble(source, origin=0x8000, limit=0xAEFF)
        for addr, b in image.items():
            self.m.sram[addr - 0x8000] = b
        self.cpu.pc = 0x8000
        self.cpu.sp = 0x00
        return a

    def type(self, text=None, keys=()):
        data = ps2.text_to_scancodes(text) if text else []
        for k in keys:
            data += ps2.press(k)
        self.kb.type_bytes(data, self.m.now)

    def run(self, cycles):
        """Advance the whole machine by `cycles` character clocks (CPU may be halted)."""
        if self.fast:
            return self._run_fast(cycles)
        m, cpu, kb = self.m, self.cpu, self.kb
        end = m.now + cycles
        while m.now < end:
            if not cpu.halted:
                cpu.cycle()
            m.now += 1
            self.frame_pos += 1
            if self.frame_pos == video.FRAME_CYCLES:
                self.frame_pos = 0
                self.frames += 1
            if self.frame_pos == video.VBL_POS:
                m.vblank = True
            if not (m.now & 31):
                kb.advance(m.now)

    def _run_fast(self, cycles, stop_pc=None):
        """Instruction-level run. Returns True if stopped at stop_pc."""
        m, cpu, kb = self.m, self.cpu, self.kb
        table = cycle_table()
        end = m.now + cycles
        vbl, frame = video.VBL_POS, video.FRAME_CYCLES
        next_kb = m.now
        while m.now < end:
            if cpu.halted:
                if stop_pc is not None:
                    return False
                n = end - m.now
            else:
                pc = cpu.pc
                if pc == stop_pc:
                    return True
                op = m.read(pc) if pc < 0x5000 or pc >= 0x6000 else 0
                n = table[op][cpu.flags]
                cpu.step_instr()
            before = self.frame_pos
            m.now += n
            self.frame_pos += n
            if before < vbl <= self.frame_pos:
                m.vblank = True
            if self.frame_pos >= frame:
                self.frame_pos -= frame
                self.frames += 1
                if self.frame_pos >= vbl:
                    m.vblank = True
            if m.now >= next_kb:
                kb.advance(m.now)
                next_kb = m.now + 64
        return False

    def run_until(self, pc=None, max_cycles=200_000_000, step=2000):
        """Run until the CPU halts or reaches `pc` (checked between instructions)."""
        start = self.m.now
        if pc is None:
            return self.run_until_halt(max_cycles)
        if self.fast:
            return self._run_fast(max_cycles, stop_pc=pc)
        while self.m.now - start < max_cycles:
            if self.cpu.halted:
                return False
            self.run(1)
            if self.cpu.step == 0 and self.cpu.pc == pc:
                return True
        return False

    def run_until_halt(self, max_cycles=50_000_000):
        start = self.m.now
        while not self.cpu.halted and self.m.now - start < max_cycles:
            self.run(1000)
        return self.cpu.halted

    def screen(self):
        return video.render(self.m.vram, self.m.font, self.m.scroll_x, self.m.scroll_y)

    def screenshot(self, path, tint="green", scale=1):
        video.write_png(path, self.screen(), tint, scale)

    def text_row(self, row, start=0, length=80):
        """VRAM characters of one visible row as a string (tile codes <32 shown as '.')."""
        base = ((row + self.m.scroll_y) & 31) * 128
        out = []
        for c in range(start, start + length):
            ch = self.m.vram[base + ((c + self.m.scroll_x) & 127)]
            out.append(chr(ch) if 32 <= ch < 127 else ".")
        return "".join(out)
