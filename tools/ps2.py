"""PS/2 keyboard: device model, Open8 receiver hardware model, scan-code helpers.

Receiver hardware (docs/03-video-keyboard.md):
  CLK -> 74HC14 -> clocks 2x 74HC164 (11-bit frame) and a 74HC161 bit counter on each
  falling CLK edge. At 11 bits READY (74HC74) sets and a 74HC05 open-drain output holds
  CLK low (inhibit) so the keyboard buffers further bytes. Reading KBD_DATA ($5000)
  returns frame bits 1-8 (the data byte), clears READY and the counter, releasing CLK.
  KBD_STATUS ($5001): b0 READY, b1 parity bit, b2 start bit, b3 stop bit.
  An RC + Schmitt timeout clears a partial frame after ~2 ms without CLK edges.
Times are in CPU cycles (3.147 MHz -> 318 ns).
"""
CPU_HZ = 3_146_875
BIT_CYCLES = 252            # 12.5 kHz PS/2 clock -> 80 us per bit
INHIBIT_RESUME = 160        # keyboard waits ~50 us after CLK is released
TIMEOUT_CYCLES = 6300       # ~2 ms
KBD_BUFFER = 16             # typical keyboard-internal buffer
OVERRUN = 0x00              # scan code set 2 buffer-overrun code


def frame_bits(byte, parity_error=False):
    data = [(byte >> i) & 1 for i in range(8)]
    parity = 1 - (sum(data) & 1)                 # odd parity
    if parity_error:
        parity ^= 1
    return [0] + data + [parity, 1]


class Receiver:
    def __init__(self):
        self.shift = 0          # 16-bit chain of two 74HC164 (newest bit enters at bit 15)
        self.count = 0
        self.ready = False
        self.last_edge = 0

    @property
    def inhibit(self):
        return self.ready

    def falling_edge(self, data_bit, now):
        if self.ready:
            return              # CLK is held low; no edges can occur
        if self.count and now - self.last_edge > TIMEOUT_CYCLES:
            self.count = 0      # stale partial frame cleared by the timeout circuit
        self.last_edge = now
        self.shift = ((self.shift >> 1) | (data_bit << 15)) & 0xFFFF
        self.count += 1
        if self.count == 11:
            self.ready = True

    def frame(self):
        """Bits as wired to the CPU-side buffers after 11 shifts."""
        bits = [(self.shift >> (5 + i)) & 1 for i in range(11)]   # bit 5 = start
        return bits

    def read_data(self):
        bits = self.frame()
        v = sum(b << i for i, b in enumerate(bits[1:9]))
        self.ready = False
        self.count = 0
        return v

    def status(self, now):
        if self.count and not self.ready and now - self.last_edge > TIMEOUT_CYCLES:
            self.count = 0
        bits = self.frame()
        return (1 if self.ready else 0) | (bits[9] << 1) | (bits[0] << 2) | (bits[10] << 3)


class Keyboard:
    """Keyboard side: sends queued bytes, honours CLK inhibit, has a finite buffer."""

    def __init__(self, receiver):
        self.rx = receiver
        self.buffer = []
        self.overrun_pending = False
        self.frame = None
        self.byte = None
        self.bit = 0
        self.next_time = 0
        self.inhibited_since = None

    def type_bytes(self, data, now=0):
        for b in data:
            if len(self.buffer) >= KBD_BUFFER:
                self.overrun_pending = True
            else:
                self.buffer.append(b)
        if self.frame is None:
            self.next_time = max(self.next_time, now)

    def inject_glitch(self, now):
        """A single noise pulse on CLK (tests the receiver timeout)."""
        self.rx.falling_edge(1, now)

    def advance(self, now):
        """Process every keyboard event up to time `now`."""
        while True:
            if self.rx.inhibit:
                if self.inhibited_since is None:
                    self.inhibited_since = now
                if self.frame is not None:      # host inhibited mid-frame: abort and
                    self.buffer.insert(0, self.byte)   # retransmit the byte later (PS/2 spec)
                    self.frame = None
                return
            if self.inhibited_since is not None:
                self.next_time = max(self.next_time, now + INHIBIT_RESUME)
                self.inhibited_since = None
            if self.frame is None:
                if not self.buffer and not self.overrun_pending:
                    return
                if self.next_time > now:
                    return
                if self.buffer:
                    byte = self.buffer.pop(0)
                else:
                    byte, self.overrun_pending = OVERRUN, False
                self.frame, self.bit, self.byte = frame_bits(byte), 0, byte
            if self.next_time > now:
                return
            self.rx.falling_edge(self.frame[self.bit], self.next_time)
            self.bit += 1
            self.next_time += BIT_CYCLES
            if self.bit == 11:
                self.frame = None
                self.next_time += BIT_CYCLES        # idle gap before the next frame


# ------------------------------------------------------------------ scan code set 2
KEYS = {
    "a": 0x1C, "b": 0x32, "c": 0x21, "d": 0x23, "e": 0x24, "f": 0x2B, "g": 0x34, "h": 0x33,
    "i": 0x43, "j": 0x3B, "k": 0x42, "l": 0x4B, "m": 0x3A, "n": 0x31, "o": 0x44, "p": 0x4D,
    "q": 0x15, "r": 0x2D, "s": 0x1B, "t": 0x2C, "u": 0x3C, "v": 0x2A, "w": 0x1D, "x": 0x22,
    "y": 0x35, "z": 0x1A, "0": 0x45, "1": 0x16, "2": 0x1E, "3": 0x26, "4": 0x25, "5": 0x2E,
    "6": 0x36, "7": 0x3D, "8": 0x3E, "9": 0x46, "`": 0x0E, "-": 0x4E, "=": 0x55, "\\": 0x5D,
    "[": 0x54, "]": 0x5B, ";": 0x4C, "'": 0x52, ",": 0x41, ".": 0x49, "/": 0x4A, " ": 0x29,
    "\n": 0x5A, "\t": 0x0D, "\b": 0x66,
}
SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
           "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";",
           '"': "'", "<": ",", ">": ".", "?": "/", "~": "`"}
SPECIAL = {"ESC": 0x76, "F1": 0x05, "F2": 0x06, "F3": 0x04, "F4": 0x0C, "F5": 0x03,
           "F6": 0x0B, "F7": 0x83, "F8": 0x0A, "F9": 0x01, "F10": 0x09, "F11": 0x78,
           "F12": 0x07, "LSHIFT": 0x12, "RSHIFT": 0x59, "LCTRL": 0x14, "LALT": 0x11,
           "CAPS": 0x58}
EXTENDED = {"UP": 0x75, "DOWN": 0x72, "LEFT": 0x6B, "RIGHT": 0x74, "HOME": 0x6C,
            "END": 0x69, "PGUP": 0x7D, "PGDN": 0x7A, "INSERT": 0x70, "DELETE": 0x71,
            "RCTRL": 0x14, "RALT": 0x11}


def press(name):
    """Make + break bytes for one named key (no modifiers)."""
    if name in EXTENDED:
        c = EXTENDED[name]
        return [0xE0, c, 0xE0, 0xF0, c]
    c = SPECIAL.get(name, KEYS.get(name))
    if c is None:
        raise KeyError(name)
    return [c, 0xF0, c]


def text_to_scancodes(text):
    out = []
    for ch in text:
        if ch in KEYS:
            out += press(ch)
        elif ch.isalpha() and ch.lower() in KEYS:
            out += [0x12] + press(ch.lower()) + [0xF0, 0x12]
        elif ch in SHIFTED:
            out += [0x12] + press(SHIFTED[ch]) + [0xF0, 0x12]
        else:
            raise KeyError(repr(ch))
    return out


class Decoder:
    """Reference set-2 decoder (golden model for the firmware driver).

    feed(byte) returns an event or None. Events: ('char', 'a'), ('key', 'UP'),
    ('down', code, extended) / ('up', code, extended) are also recorded in self.down.
    """
    BY_CODE = {v: k for k, v in KEYS.items()}
    BY_CODE_SHIFTED = {}
    for s, base in SHIFTED.items():
        BY_CODE_SHIFTED[KEYS[base]] = s
    EXT_BY_CODE = {v: k for k, v in EXTENDED.items()}
    SPECIAL_BY_CODE = {v: k for k, v in SPECIAL.items()}

    def __init__(self):
        self.ext = self.brk = False
        self.shift = self.ctrl = self.caps = False
        self.down = set()

    def feed(self, b):
        if b == 0xE0:
            self.ext = True
            return None
        if b == 0xF0:
            self.brk = True
            return None
        ext, brk = self.ext, self.brk
        self.ext = self.brk = False
        key = (b, ext)
        if brk:
            self.down.discard(key)
        else:
            self.down.add(key)
        if b in (0x12, 0x59) and not ext:
            self.shift = not brk
            return None
        if b == 0x14:
            self.ctrl = not brk
            return None
        if brk:
            return None
        if b == 0x58 and not ext:
            self.caps = not self.caps
            return None
        if ext:
            name = self.EXT_BY_CODE.get(b)
            return ("key", name) if name else None
        if b in self.SPECIAL_BY_CODE:
            return ("key", self.SPECIAL_BY_CODE[b])
        ch = self.BY_CODE.get(b)
        if ch is None:
            return None
        if self.shift and b in self.BY_CODE_SHIFTED:
            ch = self.BY_CODE_SHIFTED[b]
        elif ch.isalpha() and (self.shift ^ self.caps):
            ch = ch.upper()
        if self.ctrl and ch.isalpha():
            return ("ctrl", ch.upper())
        return ("char", ch)
