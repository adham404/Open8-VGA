"""Model of the Microchip 25LC512 SPI EEPROM (64 KiB) as wired on Open8-VGA.

Wiring (docs/06-eeprom.md): OUT_PORT bit 0 = SCK, bit 1 = MOSI (SI), bit 2 = /CS;
IN_PORT bit 0 = MISO (SO). /WP and /HOLD tied high. SPI mode 0, MSB first: the
EEPROM samples SI on the rising SCK edge and changes SO after the falling edge.

Modelled commands (datasheet DS20005185): READ $03, WRITE $02, WREN $06, WRDI $04,
RDSR $05, WRSR $01 (accepted, ignored). Erased memory reads $FF. A WRITE needs a
preceding WREN, writes inside one 128-byte page (the address wraps within the page),
and starts a self-timed write cycle (5 ms) when /CS goes high; the WEL latch clears.
During the write cycle only RDSR is answered (status bit 0 = WIP).
"""
SIZE = 65536
PAGE = 128
WRITE_CYCLES = 15735          # 5 ms at 3.147 MHz


class EEPROM25LC512:
    def __init__(self, data=None):
        self.mem = bytearray(data if data is not None else b"\xff" * SIZE)
        self.cs = True            # /CS high = deselected
        self.sck = 0
        self.si = 0
        self.so = 1
        self.wel = False
        self.busy_until = 0
        self._reset_frame()
        self.writes = 0           # completed write cycles (for tests)

    def _reset_frame(self):
        self.shift_in = 0
        self.bits = 0
        self.rx = []              # bytes received in this frame
        self.out_byte = 0xFF
        self.out_bits = 0
        self.addr = 0
        self.page_buf = {}

    def power_cycle(self):
        """Power off and on: memory kept, latches and any write-cycle timer reset
        (the next machine's cycle counter starts again at 0)."""
        self.cs, self.sck, self.so, self.wel, self.busy_until = True, 0, 1, False, 0
        self._reset_frame()

    def busy(self, now):
        return now < self.busy_until

    def pins(self, out_port, now):
        """Update from a write to OUT_PORT."""
        sck, si, cs = out_port & 1, (out_port >> 1) & 1, bool(out_port & 4)
        if cs and not self.cs:                      # rising /CS ends a frame
            self._end_frame(now)
        if not cs and self.cs:                      # falling /CS starts a frame
            self._reset_frame()
            self.so = 1
        self.cs = cs
        if not cs:
            if sck and not self.sck:                # rising edge: sample SI
                self._clock_in(si, now)
            elif not sck and self.sck:              # falling edge: shift SO
                self._clock_out()
        self.sck, self.si = sck, si

    def miso(self):
        return 1 if self.cs else self.so

    def _clock_in(self, bit, now):
        self.shift_in = ((self.shift_in << 1) | bit) & 0xFF
        self.bits += 1
        if self.bits == 8:
            self.bits = 0
            self._byte(self.shift_in, now)

    def _clock_out(self):
        if self.out_bits:
            self.so = (self.out_byte >> 7) & 1
            self.out_byte = (self.out_byte << 1) & 0xFF
            self.out_bits -= 1
        else:
            self.so = 1

    def _load_out(self, value):
        """Next byte to shift out: bit 7 appears after the next falling SCK edge."""
        self.out_byte = value
        self.out_bits = 8

    def _byte(self, b, now):
        self.rx.append(b)
        cmd = self.rx[0]
        n = len(self.rx)
        if self.busy(now) and cmd != 0x05:
            return                                   # ignored during a write cycle
        if cmd == 0x05:                               # RDSR: status repeats
            self._load_out((1 if self.busy(now) else 0) | (2 if self.wel else 0))
        elif cmd == 0x03:                             # READ addr16, then data stream
            if n == 3:
                self.addr = (self.rx[1] << 8) | self.rx[2]
            if n >= 3:
                self._load_out(self.mem[self.addr])
                self.addr = (self.addr + 1) & 0xFFFF
        elif cmd == 0x02:                             # WRITE addr16, data (page wrap)
            if n == 3:
                self.addr = (self.rx[1] << 8) | self.rx[2]
            elif n > 3 and self.wel:
                self.page_buf[self.addr] = b
                self.addr = (self.addr & ~(PAGE - 1)) | ((self.addr + 1) & (PAGE - 1))

    def _end_frame(self, now):
        if not self.rx or (self.busy(now) and self.rx[0] != 0x05):
            return
        cmd = self.rx[0]
        if cmd == 0x06 and len(self.rx) == 1:
            self.wel = True
        elif cmd == 0x04:
            self.wel = False
        elif cmd == 0x02 and self.wel and len(self.rx) > 3 and self.bits == 0:
            for a, v in self.page_buf.items():
                self.mem[a] = v
            self.wel = False
            self.busy_until = now + WRITE_CYCLES
            self.writes += 1
        elif cmd in (0x02, 0x01):
            self.wel = False
