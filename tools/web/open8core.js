// Open8-VGA emulator core (JavaScript port of tools/sim.py RefCPU + Machine,
// tools/ps2.py Receiver + Keyboard and tools/system.py _run_fast).
// It must stay behaviourally identical: tests/test_web.py compares it with the
// Python simulator state-for-state.   Author: Adham Elshafei
"use strict";

const O8 = (function () {
  const SRAM_BASE = 0x8000, PROTECT_BASE = 0xB000, STACK_PAGE = 0xAF;
  const FRAME_CYCLES = 52500, VBL_POS = 480 * 100 + 2;
  const BIT_CYCLES = 252, INHIBIT_RESUME = 160, TIMEOUT_CYCLES = 6300, KBD_BUFFER = 16, OVERRUN = 0;

  function frameBits(byte) {
    const bits = [0];
    let ones = 0;
    for (let i = 0; i < 8; i++) { const b = (byte >> i) & 1; bits.push(b); ones += b; }
    bits.push(1 - (ones & 1));
    bits.push(1);
    return bits;
  }

  class Receiver {
    constructor() { this.shift = 0; this.count = 0; this.ready = false; this.lastEdge = 0; }
    get inhibit() { return this.ready; }
    fallingEdge(bit, now) {
      if (this.ready) return;
      if (this.count && now - this.lastEdge > TIMEOUT_CYCLES) this.count = 0;
      this.lastEdge = now;
      this.shift = ((this.shift >> 1) | (bit << 15)) & 0xFFFF;
      this.count += 1;
      if (this.count === 11) this.ready = true;
    }
    frame() { const b = []; for (let i = 0; i < 11; i++) b.push((this.shift >> (5 + i)) & 1); return b; }
    readData() {
      const b = this.frame();
      let v = 0;
      for (let i = 1; i <= 8; i++) v |= b[i] << (i - 1);
      this.ready = false; this.count = 0;
      return v;
    }
    status(now) {
      if (this.count && !this.ready && now - this.lastEdge > TIMEOUT_CYCLES) this.count = 0;
      const b = this.frame();
      return (this.ready ? 1 : 0) | (b[9] << 1) | (b[0] << 2) | (b[10] << 3);
    }
  }

  class Keyboard {
    constructor(rx) {
      this.rx = rx; this.buffer = []; this.overrunPending = false;
      this.frame = null; this.byte = null; this.bit = 0; this.nextTime = 0; this.inhibitedSince = null;
    }
    typeBytes(data, now) {
      for (const b of data) {
        if (this.buffer.length >= KBD_BUFFER) this.overrunPending = true;
        else this.buffer.push(b);
      }
      if (this.frame === null) this.nextTime = Math.max(this.nextTime, now);
    }
    advance(now) {
      for (;;) {
        if (this.rx.inhibit) {
          if (this.inhibitedSince === null) this.inhibitedSince = now;
          if (this.frame !== null) { this.buffer.unshift(this.byte); this.frame = null; }
          return;
        }
        if (this.inhibitedSince !== null) {
          this.nextTime = Math.max(this.nextTime, now + INHIBIT_RESUME);
          this.inhibitedSince = null;
        }
        if (this.frame === null) {
          if (!this.buffer.length && !this.overrunPending) return;
          if (this.nextTime > now) return;
          let byte;
          if (this.buffer.length) byte = this.buffer.shift();
          else { byte = OVERRUN; this.overrunPending = false; }
          this.frame = frameBits(byte); this.bit = 0; this.byte = byte;
        }
        if (this.nextTime > now) return;
        this.rx.fallingEdge(this.frame[this.bit], this.nextTime);
        this.bit += 1;
        this.nextTime += BIT_CYCLES;
        if (this.bit === 11) { this.frame = null; this.nextTime += BIT_CYCLES; }
      }
    }
  }

  // 25LC512 SPI EEPROM: port of tools/eeprom.py (keep identical)
  const EE_SIZE = 65536, EE_PAGE = 128, EE_WRITE_CYCLES = 15735;
  class EEPROM {
    constructor(data) {
      this.mem = new Uint8Array(EE_SIZE).fill(0xFF);
      if (data) this.mem.set(data.subarray(0, EE_SIZE));
      this.cs = true; this.sck = 0; this.si = 0; this.so = 1; this.wel = false;
      this.busyUntil = 0; this.writes = 0; this.dirty = false;
      this.resetFrame();
    }
    resetFrame() {
      this.shiftIn = 0; this.bits = 0; this.rx = []; this.outByte = 0xFF; this.outBits = 0;
      this.addr = 0; this.pageBuf = new Map();
    }
    powerCycle() { this.cs = true; this.sck = 0; this.so = 1; this.wel = false; this.busyUntil = 0; this.resetFrame(); }
    busy(now) { return now < this.busyUntil; }
    pins(out, now) {
      const sck = out & 1, si = (out >> 1) & 1, cs = (out & 4) !== 0;
      if (cs && !this.cs) this.endFrame(now);
      if (!cs && this.cs) { this.resetFrame(); this.so = 1; }
      this.cs = cs;
      if (!cs) {
        if (sck && !this.sck) this.clockIn(si, now);
        else if (!sck && this.sck) this.clockOut();
      }
      this.sck = sck; this.si = si;
    }
    miso() { return this.cs ? 1 : this.so; }
    clockIn(bit, now) {
      this.shiftIn = ((this.shiftIn << 1) | bit) & 0xFF;
      this.bits += 1;
      if (this.bits === 8) { this.bits = 0; this.byte(this.shiftIn, now); }
    }
    clockOut() {
      if (this.outBits) {
        this.so = (this.outByte >> 7) & 1;
        this.outByte = (this.outByte << 1) & 0xFF;
        this.outBits -= 1;
      } else this.so = 1;
    }
    loadOut(v) { this.outByte = v; this.outBits = 8; }
    byte(b, now) {
      this.rx.push(b);
      const cmd = this.rx[0], n = this.rx.length;
      if (this.busy(now) && cmd !== 0x05) return;
      if (cmd === 0x05) this.loadOut((this.busy(now) ? 1 : 0) | (this.wel ? 2 : 0));
      else if (cmd === 0x03) {
        if (n === 3) this.addr = (this.rx[1] << 8) | this.rx[2];
        if (n >= 3) { this.loadOut(this.mem[this.addr]); this.addr = (this.addr + 1) & 0xFFFF; }
      } else if (cmd === 0x02) {
        if (n === 3) this.addr = (this.rx[1] << 8) | this.rx[2];
        else if (n > 3 && this.wel) {
          this.pageBuf.set(this.addr, b);
          this.addr = (this.addr & ~(EE_PAGE - 1)) | ((this.addr + 1) & (EE_PAGE - 1));
        }
      }
    }
    endFrame(now) {
      if (!this.rx.length || (this.busy(now) && this.rx[0] !== 0x05)) return;
      const cmd = this.rx[0];
      if (cmd === 0x06 && this.rx.length === 1) this.wel = true;
      else if (cmd === 0x04) this.wel = false;
      else if (cmd === 0x02 && this.wel && this.rx.length > 3 && this.bits === 0) {
        for (const [a, v] of this.pageBuf) this.mem[a] = v;
        this.wel = false; this.busyUntil = now + EE_WRITE_CYCLES; this.writes += 1; this.dirty = true;
      } else if (cmd === 0x02 || cmd === 0x01) this.wel = false;
    }
  }

  class Machine {
    constructor(flash) {
      this.flash = new Uint8Array(1 << 17).fill(0xFF);
      this.flash.set(flash.subarray(0, 1 << 17));
      this.sram = new Uint8Array(0x8000);
      this.vram = new Uint8Array(0x1000);
      this.font = new Uint8Array(0x1000);
      this.bank = 0; this.scrollX = 0; this.scrollY = 0; this.outPort = 0; this.inPort = 0xFF;
      this.vblank = false; this.trap = false; this.violation = false;
      this.now = 0;
      this.rx = new Receiver();
      this.kb = new Keyboard(this.rx);
      this.eeprom = new EEPROM();
    }
    read(a) {
      a &= 0xFFFF;
      if (a < 0x4000) return this.flash[a];
      if (a < 0x5000) return this.flash[(this.bank << 12) | (a & 0xFFF)];
      if (a < 0x6000) return this.ioRead(a & 7);
      if (a < 0x7000) return this.vram[a & 0xFFF];
      if (a < 0x8000) return this.font[a & 0xFFF];
      return this.sram[a - SRAM_BASE];
    }
    write(a, v, fromRam) {
      a &= 0xFFFF; v &= 0xFF;
      if (a < 0x5000) return;
      if (a < 0x6000) this.ioWrite(a & 7, v);
      else if (a < 0x7000) this.vram[a & 0xFFF] = v;
      else if (a < 0x8000) this.font[a & 0xFFF] = v;
      else if (fromRam && a >= PROTECT_BASE) { this.violation = true; }
      else this.sram[a - SRAM_BASE] = v;
    }
    ioRead(r) {
      if (r === 0 || r === 1) {
        this.kb.advance(this.now);
        return r === 0 ? this.rx.readData() : this.rx.status(this.now);
      }
      if (r === 2) {
        const v = (this.vblank ? 1 : 0) | (this.trap ? 2 : 0) | (this.violation ? 4 : 0);
        this.vblank = false;
        return v;
      }
      if (r === 7) return this.eeprom ? (this.inPort & 0xFE) | this.eeprom.miso() : this.inPort;
      return 0xFF;
    }
    ioWrite(r, v) {
      if (r === 2) { this.trap = false; this.violation = false; }
      else if (r === 3) this.bank = v & 0x1F;
      else if (r === 4) this.scrollX = v & 0x7F;
      else if (r === 5) this.scrollY = v & 0x1F;
      else if (r === 6) { this.outPort = v; if (this.eeprom) this.eeprom.pins(v, this.now); }
    }
  }

  // ---------------------------------------------------------------- CPU
  // isa: array[256] of [mnemonic, op1, op2] or null; cycles: Uint8Array(256*16)
  class CPU {
    constructor(m, isa, cycles) {
      this.m = m; this.isa = isa; this.cycles = cycles;
      this.a = 0; this.b = 0; this.x = 0; this.sp = 0; this.pc = 0; this.flags = 0;
      this.halted = false; this.fromRam = false;
    }
    fetch8() { const v = this.m.read(this.pc); this.pc = (this.pc + 1) & 0xFFFF; return v; }
    fetch16() { const lo = this.fetch8(); return lo | (this.fetch8() << 8); }
    push(v) { this.sp = (this.sp - 1) & 0xFF; this.m.write((STACK_PAGE << 8) | this.sp, v, this.fromRam); }
    pop() { const v = this.m.read((STACK_PAGE << 8) | this.sp); this.sp = (this.sp + 1) & 0xFF; return v; }
    setZN(r, c, v) { this.flags = (c ? 1 : 0) | (r === 0 ? 2 : 0) | (r & 0x80 ? 4 : 0) | (v ? 8 : 0); }
    get(n) {
      switch (n) {
        case "A": return this.a; case "B": return this.b; case "XL": return this.x & 0xFF;
        case "XH": return this.x >> 8; case "SP": return this.sp;
      }
      throw new Error(n);
    }
    put(n, v) {
      v &= 0xFF;
      switch (n) {
        case "A": this.a = v; break; case "B": this.b = v; break;
        case "XL": this.x = (this.x & 0xFF00) | v; break;
        case "XH": this.x = (this.x & 0x00FF) | (v << 8); break;
        case "SP": this.sp = v; break;
      }
    }
    operand(kind) {
      if (kind === "imm8") return this.fetch8();
      if (kind === "abs") return this.m.read(this.fetch16());
      if (kind === "ind") return this.m.read(this.x);
      if (kind === "B") return this.b;
      throw new Error(kind);
    }
    step() {
      const at = this.pc, m = this.m;
      const op = this.fetch8();
      this.fromRam = (at & 0x8000) !== 0;
      const ins = this.isa[op];
      if (!ins) {
        this.push(this.pc >> 8); this.push(this.pc & 0xFF);
        this.pc = 0; m.trap = true; return;
      }
      const mn = ins[0], o1 = ins[1], o2 = ins[2];
      const cIn = this.flags & 1;
      let r, c, v, b, a, s;
      switch (mn) {
        case "HLT": this.halted = true; return;
        case "NOP": return;
        case "LD":
          if (o1 === "A" || o1 === "B") {
            if (o2 === "imm8") v = this.fetch8();
            else if (o2 === "abs") v = m.read(this.fetch16());
            else { v = m.read(this.x); if (o2 === "indinc") this.x = (this.x + 1) & 0xFFFF; }
            this.put(o1, v);
          } else if (o1 === "X") this.x = this.fetch16();
          else this.sp = this.fetch8();
          return;
        case "ST":
          v = this.get(o1);
          if (o2 === "abs") m.write(this.fetch16(), v, this.fromRam);
          else { m.write(this.x, v, this.fromRam); if (o2 === "indinc") this.x = (this.x + 1) & 0xFFFF; }
          return;
        case "MOV": this.put(o1, this.get(o2)); return;
        case "ADD":
          if (o1 === "X") {
            s = this.x + this.a; this.x = s & 0xFFFF;
            this.flags = (this.flags & ~1) | (s > 0xFFFF ? 1 : 0); return;
          }
        // falls through
        case "ADC":
          b = this.operand(o2); a = this.a;
          s = a + b + (mn === "ADC" ? cIn : 0); r = s & 0xFF;
          this.setZN(r, s > 0xFF, (a ^ r) & (b ^ r) & 0x80); this.a = r; return;
        case "SUB": case "SBC": case "CMP":
          b = this.operand(o2); a = this.a;
          s = a - b - (mn === "SBC" ? cIn : 0); r = s & 0xFF;
          this.setZN(r, s < 0, (a ^ b) & (a ^ r) & 0x80);
          if (mn !== "CMP") this.a = r; return;
        case "AND": case "OR": case "XOR":
          b = this.operand(o2);
          r = mn === "AND" ? this.a & b : mn === "OR" ? this.a | b : this.a ^ b;
          this.setZN(r, 0, 0); this.a = r; return;
        case "NOT": case "SHL": case "SHR": case "ROL": case "ROR": case "INC": case "DEC":
          if (o1 === "X") {
            if (mn === "INC") { this.x = (this.x + 1) & 0xFFFF; return; }
            const borrow = this.x === 0;
            this.x = (this.x - 1) & 0xFFFF;
            this.flags = (this.flags & ~1) | (borrow ? 1 : 0); return;
          }
          v = this.get(o1); c = 0; let ov = 0;
          if (mn === "NOT") r = ~v & 0xFF;
          else if (mn === "SHL") { r = (v << 1) & 0xFF; c = v >> 7; }
          else if (mn === "SHR") { r = v >> 1; c = v & 1; }
          else if (mn === "ROL") { r = ((v << 1) & 0xFF) | cIn; c = v >> 7; }
          else if (mn === "ROR") { r = (v >> 1) | (cIn << 7); c = v & 1; }
          else if (mn === "INC") { r = (v + 1) & 0xFF; c = v === 0xFF; ov = v === 0x7F; }
          else { r = (v - 1) & 0xFF; c = v === 0; ov = v === 0x80; }
          this.setZN(r, c, ov); this.put(o1, r); return;
        case "CLC": this.flags &= ~1; return;
        case "SEC": this.flags |= 1; return;
        case "JMP": this.pc = o1 === "X" ? this.x : this.fetch16(); return;
        case "JZ": case "JNZ": case "JC": case "JNC": case "JN": case "JNN": case "JV": case "JNV": {
          const target = this.fetch16();
          const bit = { Z: 2, C: 1, N: 4, V: 8 }[mn[mn.length - 1]];
          const want = mn === "JN" || !mn.startsWith("JN");
          if (((this.flags & bit) !== 0) === want) this.pc = target;
          return;
        }
        case "CALL": {
          const target = o1 === "X" ? this.x : this.fetch16();
          this.push(this.pc >> 8); this.push(this.pc & 0xFF); this.pc = target; return;
        }
        case "RET": { const lo = this.pop(); this.pc = lo | (this.pop() << 8); return; }
        case "PUSH":
          if (o1 === "X") { this.push(this.x >> 8); this.push(this.x & 0xFF); }
          else this.push(this.get(o1));
          return;
        case "POP":
          if (o1 === "X") { const lo = this.pop(); this.x = lo | (this.pop() << 8); }
          else this.put(o1, this.pop());
          return;
        case "PUSHF": this.push(this.flags); return;
        case "POPF": this.flags = this.pop() & 0x0F; return;
      }
      throw new Error("unimplemented " + mn);
    }
  }

  // ---------------------------------------------------------------- system
  class System {
    constructor(flash, isa, cycles) {
      this.m = new Machine(flash);
      this.cpu = new CPU(this.m, isa, cycles);
      this.framePos = 0; this.frames = 0;
    }
    // Same algorithm as tools/system.py System._run_fast (keyboard serviced every 64 cycles).
    run(cycles, stopPc) {
      const m = this.m, cpu = this.cpu, kb = m.kb, table = cpu.cycles;
      const end = m.now + cycles;
      let nextKb = m.now;
      while (m.now < end) {
        let n;
        if (cpu.halted) {
          if (stopPc !== undefined) return false;
          n = end - m.now;
        } else {
          const pc = cpu.pc;
          if (pc === stopPc) return true;
          const op = (pc < 0x5000 || pc >= 0x6000) ? m.read(pc) : 0;
          n = table[op * 16 + cpu.flags];
          cpu.step();
        }
        const before = this.framePos;
        m.now += n;
        this.framePos += n;
        if (before < VBL_POS && VBL_POS <= this.framePos) m.vblank = true;
        if (this.framePos >= FRAME_CYCLES) {
          this.framePos -= FRAME_CYCLES;
          this.frames += 1;
          if (this.framePos >= VBL_POS) m.vblank = true;
        }
        if (m.now >= nextKb) { kb.advance(m.now); nextKb = m.now + 64; }
      }
      return false;
    }
    reset() {           // the RESET button: PC <- 0, latches cleared, RAM kept
      this.cpu.pc = 0; this.cpu.halted = false;
      this.m.trap = false; this.m.violation = false;
      this.m.bank = 0; this.m.scrollX = 0; this.m.scrollY = 0; this.m.outPort = 0;
    }
    // Render the visible 640x480 frame into an RGBA buffer.
    render(rgba, fg, bg) {
      const m = this.m;
      let p = 0;
      for (let y = 0; y < 480; y++) {
        const tr = ((y >> 4) + m.scrollY) & 31, fy = y & 15;
        for (let col = 0; col < 80; col++) {
          const ch = m.vram[tr * 128 + ((col + m.scrollX) & 127)];
          const bits = m.font[ch * 16 + fy];
          for (let i = 7; i >= 0; i--) {
            const on = (bits >> i) & 1, cl = on ? fg : bg;
            rgba[p] = cl[0]; rgba[p + 1] = cl[1]; rgba[p + 2] = cl[2]; rgba[p + 3] = 255;
            p += 4;
          }
        }
      }
    }
    stateHash() {      // FNV-1a over registers and all RAM, for cross-checking with Python
      let h = 0x811c9dc5 >>> 0;
      const mix = (v) => { h ^= v & 0xFF; h = Math.imul(h, 0x01000193) >>> 0; };
      const c = this.cpu, m = this.m;
      [c.a, c.b, c.x & 0xFF, c.x >> 8, c.sp, c.pc & 0xFF, c.pc >> 8, c.flags, c.halted ? 1 : 0,
       m.bank, m.scrollX, m.scrollY, m.trap ? 1 : 0, m.violation ? 1 : 0].forEach(mix);
      for (const arr of [m.sram, m.vram, m.font]) for (let i = 0; i < arr.length; i++) mix(arr[i]);
      if (m.eeprom) for (let i = 0; i < m.eeprom.mem.length; i++) mix(m.eeprom.mem[i]);
      return h >>> 0;
    }
  }

  return { System, Machine, CPU, Receiver, Keyboard, EEPROM, FRAME_CYCLES };
})();

if (typeof module !== "undefined") module.exports = O8;
