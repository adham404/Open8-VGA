; Open8-VGA firmware — utilities
; Author: Adham Elshafei

; ---------------------------------------------------------------- banked ROM reader
; Reads a byte stream that may span consecutive 4 KiB flash pages through the
; $4000-$4FFF window. Set BK_PAGE and BK_ADDR ($4000-$4FFF) first.
; bget: A = next byte. Preserves B and X.
bget:
        PUSH X
        LD A, [BK_PAGE]
        ST A, [ROM_BANK]
        LD A, [BK_ADDR]
        MOV XL, A
        LD A, [BK_ADDR+1]
        MOV XH, A
        LD A, [X+]
        PUSH A
        MOV A, XH
        CMP A, #$50
        JNZ bg_same
        LD A, [BK_PAGE]
        INC A
        ST A, [BK_PAGE]
        LD A, #$40
        MOV XH, A
bg_same:
        MOV A, XL
        ST A, [BK_ADDR]
        MOV A, XH
        ST A, [BK_ADDR+1]
        POP A
        POP X
        RET

; A = page: start reading at the beginning of that page
bopen:
        ST A, [BK_PAGE]
        LD A, #$00
        ST A, [BK_ADDR]
        LD A, #$40
        ST A, [BK_ADDR+1]
        RET

; ---------------------------------------------------------------- font
; Copy the default font from flash page BANK_FONT into font RAM.
font_init:
        LD A, #BANK_FONT
        ST A, [ROM_BANK]
        LD X, #$4000
fi_l:   LD B, [X]
        MOV A, XH
        ADD A, #$30             ; $4xxx -> $7xxx
        MOV XH, A
        ST B, [X]
        MOV A, XH
        SUB A, #$30
        MOV XH, A
        INC X
        MOV A, XH
        CMP A, #$50
        JNZ fi_l
        RET

; ---------------------------------------------------------------- strings on screen
; X -> string, A = column, B = row: print through the console at that position.
print_at:
        PUSH X
        CALL r_gotoxy
        POP X
        JMP r_print

; Fill the rest of the console row with spaces (in CON_ATTR). The cursor does
; not move, so this is safe on the bottom row. Preserves B and X.
clear_eol:
        PUSH B
        PUSH X
        LD A, [CON_X]
        LD B, [CON_Y]
        CALL vaddr
        LD A, [CON_X]
        ST A, [T1]
        LD A, #' '
        OR A, [CON_ATTR]
        MOV B, A
ce_l:   LD A, [T1]
        CMP A, #80
        JNC ce_end
        ST B, [X+]
        INC A
        ST A, [T1]
        JMP ce_l
ce_end: POP X
        POP B
        RET

; Fill row B (0-29) with spaces in CON_ATTR and leave the cursor at its start.
clear_row:
        LD A, #0
        CALL r_gotoxy
        JMP clear_eol
