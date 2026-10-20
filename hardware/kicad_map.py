"""Map the Open8-VGA netlist (design.py) onto KiCad symbols/footprints and HeyPCB payloads.

Every symbol's pin table was checked against the datasheet-derived tables in lib.py
(docs/08-board.md lists them). Footprints are through-hole DIP for hand assembly;
the nine flash chips sit in sockets so they can be programmed off-board.
Author: Adham Elshafei
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import design  # noqa: E402
import lib     # noqa: E402

DIP = "Package_DIP:DIP-%d_W7.62mm"
DIPW = "Package_DIP:DIP-%d_W15.24mm"

LOGIC = {  # ptype: (KiCad symbol, footprint, MPN)
    "74HC00": ("74xx:74HC00", DIP % 14, "CD74HC00E"),
    "74HC02": ("74xx:74LS02", DIP % 14, "CD74HC02E"),
    "74HC04": ("74xx:74HC04", DIP % 14, "CD74HC04E"),
    "74AC04": ("74xx:74HC04", DIP % 14, "CD74AC04E"),
    "74HC05": ("74xx:74LS05", DIP % 14, "SN74HC05N"),
    "74HC08": ("74xx:74LS08", DIP % 14, "CD74HC08E"),
    "74AC08": ("74xx:74LS08", DIP % 14, "CD74AC08E"),
    "74HC11": ("74xx:74LS11", DIP % 14, "CD74HC11E"),
    "74HC14": ("74xx:74HC14", DIP % 14, "CD74HC14E"),
    "74HC32": ("74xx:74LS32", DIP % 14, "CD74HC32E"),
    "74HC86": ("74xx:74LS86", DIP % 14, "CD74HC86E"),
    "74HC74": ("74xx:74LS74", DIP % 14, "CD74HC74E"),
    "74AC74": ("74xx:74LS74", DIP % 14, "CD74AC74E"),
    "74HC138": ("74xx:74HC138", DIP % 16, "CD74HC138E"),
    "74AC138": ("74xx:74HC138", DIP % 16, "CD74AC138E"),
    "74HC139": ("74xx:74LS139", DIP % 16, "CD74HC139E"),
    "74AC151": ("74xx:74LS151", DIP % 16, "CD74AC151E"),
    "74HC153": ("74xx:74LS153", DIP % 16, "CD74HC153E"),
    "74HC154": ("74xx:74LS154", DIPW % 24, "CD74HC154E"),
    "74HC157": ("74xx:74LS157", DIP % 16, "CD74HC157E"),
    "74AC157": ("74xx:74LS157", DIP % 16, "CD74AC157E"),
    "74HC161": ("74xx:74LS161", DIP % 16, "CD74HC161E"),
    "74AC161": ("74xx:74LS161", DIP % 16, "CD74AC161E"),
    "74HC163": ("74xx:74LS163", DIP % 16, "CD74HC163E"),
    "74HC164": ("74xx:74HC164", DIP % 14, "CD74HC164E"),
    "74HC245": ("74xx:74HC245", DIP % 20, "CD74HC245E"),
    "74AC245": ("74xx:74HC245", DIP % 20, "CD74AC245E"),
    "74HC283": ("74xx:74LS283", DIP % 16, "CD74HC283E"),
    "74HC377": ("74xx:74LS377", DIP % 20, "CD74HC377E"),
    "74HC541": ("74xx:74LS541", DIP % 20, "CD74HC541E"),
    "74HC574": ("74xx:74LS574", DIP % 20, "CD74HC574E"),
    "74AC574": ("74xx:74LS574", DIP % 20, "CD74AC574E"),
    "SST39SF040": ("Memory_Flash:SST39SF040", "Package_DIP:DIP-32_W15.24mm_Socket", None),
    "AS6C62256": ("Memory_RAM:KM62256CLP", DIPW % 28, "AS6C62256-55PCN"),
    "AS6C6264": ("Memory_RAM:HY6264AxP", DIPW % 28, "AS6C6264-55PCN"),
}

PASSIVE = {  # ptype or prefix: (symbol, footprint)
    "R": ("Device:R", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"),
    "C": ("Device:C", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"),
    "electrolytic": ("Device:C_Polarized", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"),
    "led": ("Device:LED", "LED_THT:LED_D3.0mm"),
    "diode": ("Device:D", "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal"),
    "tvs": ("Device:D_TVS", "Diode_SMD:D_SMB"),
    "osc": ("Oscillator:CXO_DIP14", "Oscillator:Oscillator_DIP-14"),
    "supervisor": ("Power_Supervisor:MCP130-xxxDxTO", "Package_TO_SOT_THT:TO-92_Inline"),
    "button": ("Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm"),
    "slide": ("Switch:SW_SPDT", "Button_Switch_THT:SW_Slide_SPDT_Straight_CK_OS102011MS2Q"),
    "jumper": ("Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"),
    "pot": ("Device:R_Potentiometer", "Potentiometer_THT:Potentiometer_Bourns_3386P_Vertical"),
    "555": ("Timer:NE555P", "Package_DIP:DIP-8_W7.62mm"),
    "eeprom": ("Memory_EEPROM:25LCxxx", "Package_DIP:DIP-8_W7.62mm"),
    "npn": ("Transistor_BJT:Q_NPN_EBC", "Package_TO_SOT_THT:TO-92_Inline"),
    "buzzer": ("Device:Buzzer", "Buzzer_Beeper:Buzzer_12x9.5RM7.6"),
    "polyfuse": ("Device:Polyfuse", "Fuse:Fuse_1812_4532Metric"),
    "rnet": ("Device:R_Network08", "Resistor_THT:R_Array_SIP9"),
    "minidin6": ("HeyPCB_LCSC:MD-60SM", "HeyPCB_LCSC:DC-IN-TH_MD-60SM"),  # CUI MD-60SM, made from LCSC
    "de15": ("Connector:DE15_Socket_HighDensity_MountingHoles",
             "Connector_Dsub:DSUB-15-HD_Socket_Horizontal_P2.29x1.90mm_EdgePinOffset3.03mm_Housed_MountingHolesOffset4.94mm"),
    "usbc_power": ("Connector:USB_C_Receptacle_PowerOnly_6P",
                   "Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal"),
    "header2x20": ("Connector_Generic:Conn_02x20_Odd_Even",
                   "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical"),
}
PASSIVE_LCSC = {"minidin6": "C22359735"}   # parts whose land HeyPCB converts from the catalogue
PASSIVE_MPN = {"PS/2": "MD-60SM", "MCP130-450": "MCP130-450DI/TO", "25LC512": "25LC512-I/P", "NE555": "NE555P",
               "25.175MHz": "ECS-100A-251.7", "SMBJ5.0A": "SMBJ5.0A", "2N3904": "2N3904",
               "1N4148": "1N4148", "2A": "MF-MSMF200-2", "200mA": "MF-MSMF020-2"}


def part_payload(p):
    if p.kind == "logic":
        sym, fp, mpn = LOGIC[p.ptype]
        if p.ptype == "SST39SF040":
            mpn = "SST39SF040-70-4C-PHE" if "ALU" in p.note else "SST39SF010A-70-4C-PHE"
        out = {"ref": p.ref, "lib_id": sym, "footprint": fp, "value": p.ptype if "SST" not in p.ptype
               else mpn.split("-")[0], "mpn": mpn}
        nc = [str(lib.TYPES[p.ptype][0][n]) for n in lib.TYPES[p.ptype][0]
              if n not in p.conn]
        if nc:
            out["nc_pins"] = nc
        return out
    key = p.ptype if p.ptype in PASSIVE else p.ref.rstrip("0123456789")
    sym, fp = PASSIVE[key]
    out = {"ref": p.ref, "lib_id": sym, "footprint": fp, "value": p.value}
    if p.value in PASSIVE_MPN:
        out["mpn"] = PASSIVE_MPN[p.value]
    if key in PASSIVE_LCSC:
        out["lcsc_id"] = PASSIVE_LCSC[key]
    return out


def nets_payload(d):
    """[{name, pins: [REF.PIN]}] with no-connect nets dropped."""
    out = []
    for net, pins in sorted(d.nets().items()):
        if net.startswith("NC_"):
            continue
        out.append({"name": net, "pins": ["%s.%s" % (ref, num) for ref, num, _ in pins]})
    for n in out:      # the MD-60SM's three shield tabs (pads 7-9) go to ground
        if n["name"] == "GND" and any(x.startswith("J1.") for x in n["pins"]):
            n["pins"] += ["J1.7", "J1.8", "J1.9"]
    return out


def batches(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def main(out_dir):
    d = design.build()
    os.makedirs(out_dir, exist_ok=True)
    parts = [part_payload(p) for p in d.parts.values()]
    for i, b in enumerate(batches(parts, 50)):
        with open(os.path.join(out_dir, "parts_%02d.json" % i), "w") as f:
            json.dump(b, f, separators=(",", ":"))
    nets = nets_payload(d)
    # split huge nets (VCC/GND) into chunks of 150 pins: later chunks join the existing net
    flat = []
    for n in nets:
        for chunk in batches(n["pins"], 150):
            flat.append({"name": n["name"], "pins": chunk})
    for i, b in enumerate(batches(flat, 60)):
        with open(os.path.join(out_dir, "nets_%02d.json" % i), "w") as f:
            json.dump(b, f, separators=(",", ":"))
    print("%d parts in %d batches, %d nets (%d entries) in %d batches -> %s"
          % (len(parts), len(batches(parts, 50)), len(nets), len(flat), len(batches(flat, 60)), out_dir))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "build", "heypcb"))
