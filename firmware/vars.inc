; Open8-VGA firmware — system variables and constants
; Author: Adham Elshafei
;
; System RAM $FC00-$FFFF is write-protected against user programs (hardware).
; The stack page $AF00-$AFFF is shared; $AF00-$AF3F holds assembler buffers
; that are read with POP for fast comparisons (see asm_core.asm).

BUF_START   = $B000         ; editor gap buffer: text lives in [BUF_START,GAP_S) and [GAP_E,BUF_END)
BUF_END     = $F000
SYMTAB      = $F000         ; assembler symbol table: 192 slots x 16 bytes
SYM_SLOTS   = 192
SYM_SIZE    = 16
NAME_MAX    = 14            ; name length limit (name bytes per slot)
USER_LIMIT  = $AF00         ; first address a user program may not occupy (stack page)

TEXT_ROW0   = 1             ; editor text rows 1..27
TEXT_ROWS   = 27
MSG_ROW     = 28
BAR_ROW     = 29

BANK_FONT   = 4
BANK_HELP   = 5             ; pages 5-7
BANK_ASMTAB = 12            ; instruction table + predefined symbols
BANK_EXDIR  = 13            ; example directory; example texts follow

IDBUF_STK   = $00           ; SP value that makes POP read IDBUF ($AF00)
IDBUF       = $AF00         ; 21 bytes, zero padded identifier (upper case)
MNBUF_STK   = $20
MNBUF       = $AF20         ; 5 bytes, space padded mnemonic

; ---- $FC00 system variables
MAGIC       = $FC00         ; "O8" when the source buffer is valid (warm boot)
GAP_S       = $FC02
GAP_E       = $FC04
TOP         = $FC06         ; first character of the top editor line
CUR_LINE    = $FC08         ; 1-based line of the cursor
TOP_LINE    = $FC0A
WANT_COL    = $FC0C
CUR_COL     = $FC0D
CON_X       = $FC0E
CON_Y       = $FC0F
KB_FLAGS    = $FC10         ; b0 E0 seen, b1 F0 seen, b2 shift, b3 ctrl, b4 caps
KEYDOWN_MAP = $FC11         ; 16 bytes, one bit per set-2 scan code
RNG         = $FC21         ; 2
BOOT_STAT   = $FC23         ; SYS_STATUS sampled at reset
TRAP_SP     = $FC24
TRAP_PC     = $FC25         ; 2
ASM_OK      = $FC27
PROG_END    = $FC28         ; 2
MSG_PTR     = $FC2A         ; 2, message for the editor's message row (0 = none)
CUR_SAVE    = $FC2C         ; 2
CON_SCRY    = $FC2E         ; shadow of SCROLL_Y used by the console
CON_ATTR    = $FC2F         ; OR-ed into printed characters ($80 = inverse)
REDRAW      = $FC30         ; 0 = current line only, 1 = everything
SAVE_SP     = $FC31
KB_STAT     = $FC32
KB_DATA     = $FC33
KB_PAR      = $FC34
PC_CH       = $FC35
SCR_ROW     = $FC36
SCR_COL     = $FC37
T0          = $FC38
T1          = $FC39
T2          = $FC3A
T3          = $FC3B
P0          = $FC40         ; 2
P1          = $FC42         ; 2
P2          = $FC44         ; 2
VP          = $FC46         ; 2, VRAM pointer for the renderer
NUM16       = $FC48         ; 2
DIGITS      = $FC4A         ; 1 (leading-zero flag)
BK_PAGE     = $FC50
BK_ADDR     = $FC51         ; 2
HELP_PAGE   = $FC53
CNT         = $FC54         ; 2
CUR_FOUND   = $FC56
LINE_START  = $FC57         ; 2

; ---- assembler state
A_PASS      = $FC60
A_PC        = $FC61         ; 2
A_LINE      = $FC63         ; 2
A_SRC       = $FC65         ; 2
A_LSTART    = $FC67         ; 2
A_ERR       = $FC69
A_VAL       = $FC6A         ; 2
A_UNDEF     = $FC6C
A_K1        = $FC6D
A_K2        = $FC6E
A_OPV       = $FC6F         ; 2, value of the operand that carries one
A_KIND      = $FC71
A_HASH      = $FC72
A_PROBES    = $FC73
A_SLOT      = $FC74         ; 2
A_TMP       = $FC76         ; 2
A_OP        = $FC78         ; pending + / -
A_TERM      = $FC79         ; 2
A_IDLEN     = $FC7B
A_PREFIX    = $FC7C         ; < or > or 0
A_REC       = $FC7D         ; 2, instruction table record pointer
A_END       = $FC7F         ; 2
A_MNFOUND   = $FC81
A_NBYTES    = $FC82
A_COUNT     = $FC83         ; 2
A_LABEL     = $FC85         ; 1 = line had a label
A_SAVEX     = $FC86         ; 2
A_DIGIT     = $FC88
A_LPC       = $FC89         ; 2, address at the start of the line ($ in expressions)
A_FILL      = $FC8B
LBLBUF      = $AF40         ; saved copy of IDBUF while a constant's value is evaluated

; key codes (same values as the assembler's predefined K_* symbols)
KEY_BS      = 8
KEY_TAB     = 9
KEY_ENTER   = 10
KEY_ESC     = 27
