// Runs a scripted scenario on the JS emulator core and prints state hashes (see test_web.py).
const fs = require("fs");
const O8 = require("../tools/web/open8core.js");
const sc = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const b64 = (s) => Uint8Array.from(Buffer.from(s, "base64"));
const sys = new O8.System(b64(sc.flash), sc.isa, b64(sc.cycles));
const out = [];
for (let i = 0; i < sc.chunks; i++) {
  const act = sc.actions[i];
  if (act) sys.m.kb.typeBytes(act, sys.m.now);
  sys.run(sc.chunk);
  out.push([sys.m.now, sys.stateHash()]);
}
process.stdout.write(JSON.stringify(out));
