; Open8-VGA boot firmware — top level
; Author: Adham Elshafei <adham_mohsen@outlook.com>
;
; Build: python3 tools/build_firmware.py  (writes build/rom/firmware.bin)
; Flash layout (SST39SF010A, 32 pages of 4 KiB):
;   pages 0-3   $0000-$3FFF fixed code (this file)
;   page  4     font            pages 5-7  help text
;   page  12    assembler tables (seen at $4000 while assembling)
;   page  13+   example programs

        .org $0000
        JMP boot
        .include "gen/jumptable.inc"    ; runtime entry points at $0003 + 3*n

        .include "vars.inc"
        .include "boot.asm"
        .include "console.asm"
        .include "kbd.asm"
        .include "util.asm"
        .include "editor.asm"
        .include "asm_core.asm"
        .include "help.asm"
        .include "eeprom.asm"
        .include "strings.asm"
        .include "gen/keymap.inc"
fixed_end:

        .org $4000                      ; flash page BANK_ASMTAB, via the bank window
        .include "gen/asmtab.inc"
asmtab_end:
