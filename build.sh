#!/bin/sh
# Build every generated artifact and run the test suite.
# Requires only Python 3.8+ (no third-party packages).
set -e
cd "$(dirname "$0")"
python3 tools/alu.py build/rom
python3 tools/microcode.py build/rom
python3 tools/video.py build/rom/vga_timing.bin
python3 tools/font.py build/rom/font.bin
python3 tools/build_firmware.py
python3 tools/build_web.py
python3 tools/gendoc.py docs/02-isa.md
python3 -c "import sys; sys.path.insert(0, 'tools'); import system; s = system.System(); s.load_user_program(open('examples/video_demo.asm').read()); s.run_until_halt(); s.screenshot('docs/img/video_demo.png', 'green', 2)"
python3 -m unittest discover -s tests -v
