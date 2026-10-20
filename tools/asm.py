"""Open8 two-pass cross-assembler (reference implementation).

The on-board assembler implements the same syntax (minus a few directives, see
docs/02-isa.md); this one builds the firmware and is the golden model in tests.

    python3 tools/asm.py input.asm -o out.bin [--org-fill FF] [--listing out.lst]
"""
import argparse
import re
import sys

import isa

REGISTERS = {"A", "B", "X", "SP", "XL", "XH"}
ALIASES = {"JEQ": "JZ", "JNE": "JNZ", "JLO": "JC", "JHS": "JNC", "JMI": "JN", "JPL": "JNN"}

# Runtime entry points: a JMP table at $0003 + 3*i in the firmware ROM (order is ABI).
RUNTIME = ["PUTC", "PRINT", "CLS", "GOTOXY", "GETKEY", "KEYHIT", "KEYDOWN", "PRHEX",
           "PRDEC", "WAITVBL", "EXIT", "RANDOM", "DELAY", "NEWLINE", "PRDEC16"]

# Key codes returned by GETKEY/KEYHIT (ASCII for printable keys).
KEYCODES = {"K_BS": 8, "K_TAB": 9, "K_ENTER": 10, "K_ESC": 27, "K_UP": 0x80, "K_DOWN": 0x81,
            "K_LEFT": 0x82, "K_RIGHT": 0x83, "K_HOME": 0x84, "K_END": 0x85, "K_PGUP": 0x86,
            "K_PGDN": 0x87, "K_DEL": 0x88, "K_INS": 0x89}
KEYCODES.update({"K_F%d" % i: 0x8F + i for i in range(1, 13)})
# PS/2 set-2 scan codes for KEYDOWN (held-key test, used by games).
SCANCODES = {"SC_LEFT": 0x6B, "SC_RIGHT": 0x74, "SC_UP": 0x75, "SC_DOWN": 0x72,
             "SC_SPACE": 0x29, "SC_ENTER": 0x5A, "SC_ESC": 0x76, "SC_Z": 0x1A, "SC_X": 0x22,
             "SC_A": 0x1C, "SC_S": 0x1B, "SC_D": 0x23, "SC_W": 0x1D}

# Hardware symbols every program may use.
PREDEFINED = {
    "KBD_DATA": 0x5000, "KBD_STATUS": 0x5001, "SYS_STATUS": 0x5002, "ROM_BANK": 0x5003,
    "SCROLL_X": 0x5004, "SCROLL_Y": 0x5005, "OUT_PORT": 0x5006, "IN_PORT": 0x5007,
    "VRAM": 0x6000, "FONT": 0x7000, "USER_START": 0x8000, "USER_END": 0xAEFF,
    "STACK_PAGE": 0xAF00,
}
PREDEFINED.update({name: 3 + 3 * i for i, name in enumerate(RUNTIME)})
PREDEFINED.update(KEYCODES)
PREDEFINED.update(SCANCODES)

TABLE = {}
for _ins in isa.INSTRS:
    TABLE.setdefault(_ins.mnem, []).append(_ins)


class AsmError(Exception):
    def __init__(self, line, msg, file=None):
        super().__init__("line %d: %s" % (line, msg))
        self.line, self.msg, self.file = line, msg, file

    def __str__(self):
        where = "%s:%d" % (self.file, self.line) if self.file else "line %d" % self.line
        return "%s: %s" % (where, self.msg)


# ------------------------------------------------------------------ expressions
TOKEN = re.compile(r"\s*(?:(\$[0-9A-Fa-f]+|0[xX][0-9A-Fa-f]+|%[01]+|0[bB][01]+|\d+)"
                   r"|('(?:\\.|[^'])')|([A-Za-z_.][A-Za-z0-9_.]*)|(.))")


def tokenize(text, line):
    toks, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        num, ch, name, op = m.groups()
        if num is not None:
            if num.startswith("$"):
                toks.append(("num", int(num[1:], 16)))
            elif num[:2] in ("0x", "0X"):
                toks.append(("num", int(num[2:], 16)))
            elif num.startswith("%"):
                toks.append(("num", int(num[1:], 2)))
            elif num[:2] in ("0b", "0B"):
                toks.append(("num", int(num[2:], 2)))
            else:
                toks.append(("num", int(num)))
        elif ch is not None:
            body = ch[1:-1]
            body = {"\\n": "\n", "\\t": "\t", "\\0": "\0", "\\'": "'", "\\\\": "\\"}.get(body, body)
            if len(body) != 1:
                raise AsmError(line, "bad character literal %s" % ch)
            toks.append(("num", ord(body)))
        elif name is not None:
            toks.append(("name", name))
        elif op is not None and not op.isspace():
            toks.append(("op", op))
    return toks


class Expr:
    def __init__(self, toks, line, symbols, pc, final):
        self.t, self.i, self.line = toks, 0, line
        self.symbols, self.pc, self.final = symbols, pc, final
        self.unresolved = False

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        v = self.binary(0)
        if self.i != len(self.t):
            raise AsmError(self.line, "unexpected '%s' in expression" % (self.peek()[1],))
        return v

    PREC = [("|",), ("^",), ("&",), ("+", "-"), ("*", "/", "%")]

    def binary(self, level):
        if level == len(self.PREC):
            return self.unary()
        v = self.binary(level + 1)
        while self.peek()[0] == "op" and self.peek()[1] in self.PREC[level]:
            op = self.take()[1]
            r = self.binary(level + 1)
            if op == "+": v = v + r
            elif op == "-": v = v - r
            elif op == "*": v = v * r
            elif op == "/": v = v // r if r else 0
            elif op == "%": v = v % r if r else 0
            elif op == "&": v = v & r
            elif op == "|": v = v | r
            elif op == "^": v = v ^ r
        return v

    def unary(self):
        kind, val = self.peek()
        if kind == "op" and val in "-<>~":
            self.take()
            v = self.unary()
            return {"-": -v, "<": v & 0xFF, ">": (v >> 8) & 0xFF, "~": ~v}[val]
        return self.atom()

    def atom(self):
        kind, val = self.take()
        if kind == "num":
            return val
        if kind == "op" and val == "(":
            v = self.binary(0)
            if self.take() != ("op", ")"):
                raise AsmError(self.line, "missing ')'")
            return v
        if kind == "op" and val == "$":
            return self.pc
        if kind == "name":
            key = val.upper()
            if key in REGISTERS:
                raise AsmError(self.line, "register %s used in an expression" % val)
            if key in self.symbols:
                return self.symbols[key]
            if self.final:
                raise AsmError(self.line, "undefined symbol '%s'" % val)
            self.unresolved = True
            return 0
        raise AsmError(self.line, "expected a value, found '%s'" % (val,))


# ------------------------------------------------------------------ operands
def split_operands(text):
    parts, depth, cur, quote = [], 0, "", None
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def classify(op):
    """Return (kind, expression text or None)."""
    u = op.upper().replace(" ", "")
    if u in REGISTERS:
        return u, None
    if u == "[X]":
        return "ind", None
    if u == "[X+]":
        return "indinc", None
    if op.startswith("#"):
        return "imm", op[1:]
    if op.startswith("[") and op.endswith("]"):
        return "abs", op[1:-1]
    return "addr", op


def match(mnem, kinds, line):
    cands = TABLE.get(mnem)
    if not cands:
        raise AsmError(line, "unknown instruction '%s'" % mnem)
    for ins in cands:
        if len(ins.operands) != len(kinds):
            continue
        ok = True
        for want, (have, _) in zip(ins.operands, kinds):
            if want in ("imm8", "imm16"):
                ok &= have == "imm"
            else:
                ok &= want == have
        if ok:
            return ins
    forms = "; ".join(i.syntax() for i in cands)
    raise AsmError(line, "invalid operands for %s (valid: %s)" % (mnem, forms))


# ------------------------------------------------------------------ assembler
LINE = re.compile(r"^\s*(?:([A-Za-z_.][A-Za-z0-9_.]*):)?\s*(.*)$")


def strip_comment(s):
    out, quote = "", None
    for ch in s:
        if quote:
            out += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out += ch
        elif ch == ";":
            break
        else:
            out += ch
    return out.rstrip()


def parse_string(tok, line):
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        body = tok[1:-1]
        return bytes(body.encode("latin-1").decode("unicode_escape"), "latin-1")
    raise AsmError(line, "bad string %s" % tok)


class Assembler:
    def __init__(self, origin=0x8000, limit=None, predefined=True):
        self.origin, self.limit = origin, limit
        self.symbols = dict(PREDEFINED) if predefined else {}
        self.errors = []
        self.listing = []

    def value(self, text, line, pc, final):
        e = Expr(tokenize(text, line), line, self.symbols, pc, final)
        return e.parse()

    def run_pass(self, lines, final):
        pc = self.origin
        out = {}
        for fname, n, raw in lines:
            text = strip_comment(raw)
            if not text.strip():
                continue
            try:
                m = LINE.match(text)
                label, rest = m.group(1), m.group(2).strip()
                # NAME = expr / NAME .equ expr
                eq = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|\.equ\s|\.EQU\s)\s*(.+)$", text.strip())
                if eq and not label:
                    name = eq.group(1).upper()
                    v = self.value(eq.group(2), n, pc, final)
                    if not final and name in self.symbols and name not in PREDEFINED:
                        raise AsmError(n, "symbol '%s' defined twice" % eq.group(1))
                    self.symbols[name] = v
                    continue
                if label:
                    key = label.upper()
                    if key in REGISTERS or key in TABLE:
                        raise AsmError(n, "'%s' is reserved and cannot be a label" % label)
                    if not final:
                        if key in self.symbols and key not in PREDEFINED:
                            raise AsmError(n, "label '%s' defined twice" % label)
                        self.symbols[key] = pc
                if not rest:
                    continue
                parts = rest.split(None, 1)
                mnem = parts[0].upper()
                args = split_operands(parts[1]) if len(parts) > 1 else []
                if len(parts) > 1 and (parts[1].rstrip().endswith(",") or "" in args
                                       or re.search(r",\s*,", parts[1])):
                    raise AsmError(n, "syntax error: missing operand")
                start = pc
                emitted = []
                if mnem.startswith("."):
                    pc, emitted = self.directive(mnem, args, n, pc, final, out)
                else:
                    mnem = ALIASES.get(mnem, mnem)
                    kinds = [classify(a) for a in args]
                    ins = match(mnem, kinds, n)
                    emitted = [ins.opcode]
                    for want, (have, ex) in zip(ins.operands, kinds):
                        if want == "imm8":
                            v = self.value(ex, n, pc, final)
                            if final and not -128 <= v <= 255:
                                raise AsmError(n, "value %d does not fit in 8 bits" % v)
                            emitted.append(v & 0xFF)
                        elif want in ("imm16", "abs", "addr"):
                            v = self.value(ex, n, pc, final)
                            if final and not -32768 <= v <= 0xFFFF:
                                raise AsmError(n, "value %d does not fit in 16 bits" % v)
                            emitted += [v & 0xFF, (v >> 8) & 0xFF]
                    pc += len(emitted)
                    for i, b in enumerate(emitted):
                        out[start + i] = b
                if final:
                    self.listing.append((start, emitted, n, raw.rstrip(), fname))
                if self.limit is not None and pc - 1 > self.limit and emitted:
                    raise AsmError(n, "program too large: reaches $%04X, limit is $%04X"
                                   % (pc - 1, self.limit))
            except AsmError as e:
                e.file = fname
                if final or "undefined symbol" not in e.msg:
                    self.errors.append(e)
                    if len(self.errors) > 50:
                        break
        return out

    def directive(self, d, args, n, pc, final, out):
        emitted = []
        if d == ".ORG":
            if len(args) != 1:
                raise AsmError(n, ".org needs one address")
            return self.value(args[0], n, pc, True), []
        if d in (".DB", ".BYTE"):
            for a in args:
                if a.startswith('"'):
                    emitted += list(parse_string(a, n))
                else:
                    v = self.value(a, n, pc, final)
                    if final and not -128 <= v <= 255:
                        raise AsmError(n, "value %d does not fit in a byte" % v)
                    emitted.append(v & 0xFF)
        elif d in (".DW", ".WORD"):
            for a in args:
                v = self.value(a, n, pc, final)
                emitted += [v & 0xFF, (v >> 8) & 0xFF]
        elif d in (".DS", ".RES"):
            count = self.value(args[0], n, pc, True)
            fill = self.value(args[1], n, pc, True) if len(args) > 1 else 0
            emitted = [fill & 0xFF] * count
        else:
            raise AsmError(n, "unknown directive %s" % d)
        for i, b in enumerate(emitted):
            out[pc + i] = b
        return pc + len(emitted), emitted

    def expand(self, source, path, depth=0):
        """Source text -> [(file, line, text)], with .include "file" expanded."""
        import os
        out = []
        for n, raw in enumerate(source.splitlines(), 1):
            m = re.match(r'^\s*\.include\s+"([^"]+)"', raw, re.I)
            if not m:
                out.append((path, n, raw))
                continue
            if depth > 8:
                raise AsmError(n, "includes nested too deeply", path)
            base = os.path.dirname(path) if path else "."
            inc = os.path.join(base, m.group(1))
            try:
                text = open(inc).read()
            except OSError:
                raise AsmError(n, "cannot open include file %s" % m.group(1), path)
            out += self.expand(text, inc, depth + 1)
        return out

    def assemble(self, source, path=None):
        try:
            lines = self.expand(source, path)
        except AsmError as e:
            self.errors.append(e)
            return None
        self.run_pass(lines, final=False)
        if self.errors:
            return None
        image = self.run_pass(lines, final=True)
        if self.errors:
            return None
        return image


def assemble(source, origin=0x8000, limit=None, path=None):
    """Returns (image dict addr->byte, assembler). Raises AsmError on the first error."""
    a = Assembler(origin, limit)
    img = a.assemble(source, path)
    if img is None:
        raise a.errors[0]
    return img, a


def to_bytes(image, base, size, fill=0xFF):
    buf = bytearray([fill]) * size
    for addr, b in image.items():
        if not base <= addr < base + size:
            raise ValueError("byte at $%04X outside $%04X-$%04X" % (addr, base, base + size - 1))
        buf[addr - base] = b
    return buf


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--base", type=lambda s: int(s, 0), default=0x8000)
    p.add_argument("--size", type=lambda s: int(s, 0), default=None)
    p.add_argument("--listing")
    args = p.parse_args()
    a = Assembler(args.base)
    img = a.assemble(open(args.source).read(), args.source)
    if img is None:
        for e in a.errors:
            print(e, file=sys.stderr)
        sys.exit(1)
    size = args.size or (max(img) + 1 - args.base if img else 0)
    open(args.output, "wb").write(to_bytes(img, args.base, size))
    if args.listing:
        with open(args.listing, "w") as f:
            for addr, data, n, raw, _ in a.listing:
                f.write("%04X  %-12s %5d  %s\n" % (addr, " ".join("%02X" % b for b in data[:4]), n, raw))
    print("%s: %d bytes" % (args.output, size))


if __name__ == "__main__":
    main()
