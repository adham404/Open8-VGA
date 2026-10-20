; Open8-VGA firmware — text console (runtime: PUTC PRINT CLS GOTOXY NEWLINE PRHEX PRDEC ...)
; Author: Adham Elshafei
;
; The console keeps a cursor (CON_X, CON_Y) on the 80 x 30 screen. When text
; reaches the bottom it scrolls by one row using the hardware SCROLL_Y register,
; so logical row y lives in tile-map row (y + CON_SCRY) & 31.
; Calling convention for all runtime routines: A is the argument/result and is
; changed; B and X are preserved unless a routine says otherwise.

; ---------------------------------------------------------------- vaddr
; A = column, B = logical row  ->  X = VRAM address. Changes A.
vaddr:
        MOV XL, A
        LD A, [CON_SCRY]
        ADD A, B
        AND A, #31
        SHR A                   ; C = row bit 0
        JNC va_even
        ADD A, #>VRAM
        MOV XH, A
        MOV A, XL
        OR A, #$80
        MOV XL, A
        RET
va_even:
        ADD A, #>VRAM
        MOV XH, A
        RET

; ---------------------------------------------------------------- CLS
r_cls:
        PUSH B
        PUSH X
        LD A, #0
        ST A, [SCROLL_X]
        ST A, [SCROLL_Y]
        ST A, [CON_SCRY]
        ST A, [CON_X]
        ST A, [CON_Y]
        LD X, #VRAM
        LD B, #' '
cls_l:  ST B, [X+]
        ST B, [X+]
        ST B, [X+]
        ST B, [X+]
        MOV A, XH
        CMP A, #>FONT
        JNZ cls_l
        POP X
        POP B
        RET

; ---------------------------------------------------------------- GOTOXY
; A = column (0-79), B = row (0-29). Out-of-range values are clamped.
r_gotoxy:
        CMP A, #80
        JC gx_c
        LD A, #79
gx_c:   ST A, [CON_X]
        MOV A, B
        CMP A, #30
        JC gx_r
        LD A, #29
gx_r:   ST A, [CON_Y]
        RET

; ---------------------------------------------------------------- PUTC
; A = character. 10 = new line, 8 = backspace, 13 ignored.
r_putc:
        PUSH B
        PUSH X
        CMP A, #10
        JZ pc_nl
        CMP A, #13
        JZ pc_done
        CMP A, #8
        JZ pc_bs
        OR A, [CON_ATTR]
        ST A, [PC_CH]
        LD A, [CON_X]
        LD B, [CON_Y]
        CALL vaddr
        LD A, [PC_CH]
        ST A, [X]
        LD A, [CON_X]
        INC A
        ST A, [CON_X]
        CMP A, #80
        JNZ pc_done
        CALL con_newline
pc_done:
        POP X
        POP B
        RET
pc_nl:  CALL con_newline
        JMP pc_done
pc_bs:  LD A, [CON_X]
        CMP A, #0
        JZ pc_done
        DEC A
        ST A, [CON_X]
        LD B, [CON_Y]
        CALL vaddr
        LD A, #' '
        ST A, [X]
        JMP pc_done

r_newline:
        LD A, #10
        JMP r_putc

; new line, scrolling with SCROLL_Y at the bottom. Changes A, B, X.
con_newline:
        LD A, #0
        ST A, [CON_X]
        LD A, [CON_Y]
        INC A
        CMP A, #30
        JC nl_ok
        LD A, [CON_SCRY]        ; scroll: top row disappears, clear the new bottom row
        INC A
        AND A, #31
        ST A, [CON_SCRY]
        ST A, [SCROLL_Y]
        LD A, #0
        LD B, #29
        CALL vaddr
        LD B, #80
        LD A, #' '
nl_clr: ST A, [X+]
        DEC B
        JNZ nl_clr
        LD A, #29
nl_ok:  ST A, [CON_Y]
        RET

; ---------------------------------------------------------------- PRINT
; X -> zero-terminated string. Returns X just past the terminator.
r_print:
        LD A, [X+]
        CMP A, #0
        JZ pr_end
        CALL r_putc
        JMP r_print
pr_end: RET

; ---------------------------------------------------------------- PRHEX
; A -> two hex digits.
r_prhex:
        PUSH A
        SHR A
        SHR A
        SHR A
        SHR A
        CALL hexdigit
        POP A
        AND A, #$0F
hexdigit:
        CMP A, #10
        JC hd_n
        ADD A, #'A' - 10
        JMP r_putc
hd_n:   ADD A, #'0'
        JMP r_putc

; ---------------------------------------------------------------- PRDEC / PRDEC16
; PRDEC: A (0-255) in decimal.  PRDEC16: X (0-65535) in decimal.
r_prdec:
        PUSH X
        MOV XL, A
        LD A, #0
        MOV XH, A
        CALL r_prdec16
        POP X
        RET

r_prdec16:
        PUSH B
        PUSH X
        MOV A, XL
        ST A, [NUM16]
        MOV A, XH
        ST A, [NUM16+1]
        LD A, #0
        ST A, [DIGITS]
        LD X, #pow10
pd_pow: LD A, [X+]              ; power of ten, low byte
        ST A, [P0]
        LD A, [X+]
        ST A, [P0+1]
        OR A, [P0]
        JZ pd_last
        LD B, #0                ; digit
pd_sub: LD A, [NUM16]           ; NUM16 -= P0 while it does not borrow
        SUB A, [P0]
        ST A, [T0]
        LD A, [NUM16+1]
        SBC A, [P0+1]
        JC pd_dig
        ST A, [NUM16+1]
        LD A, [T0]
        ST A, [NUM16]
        INC B
        JMP pd_sub
pd_dig: MOV A, B
        OR A, [DIGITS]          ; skip leading zeros
        JZ pd_pow
        ST A, [DIGITS]
        MOV A, B
        ADD A, #'0'
        CALL r_putc
        JMP pd_pow
pd_last:
        LD A, [NUM16]
        ADD A, #'0'
        CALL r_putc
        POP X
        POP B
        RET

pow10:  .dw 10000, 1000, 100, 10, 0

; ---------------------------------------------------------------- WAITVBL / DELAY
r_waitvbl:
        LD A, [SYS_STATUS]      ; reading clears the latch
wv_l:   LD A, [SYS_STATUS]
        AND A, #1
        JZ wv_l
        RET

; A = number of frames (1/60 s each) to wait
r_delay:
        CMP A, #0
        JZ dl_end
        PUSH B
        MOV B, A
dl_l:   CALL r_waitvbl
        DEC B
        JNZ dl_l
        POP B
dl_end: RET

; ---------------------------------------------------------------- RANDOM
; A = pseudo-random byte (16-bit Galois LFSR, 8 steps).
r_random:
        PUSH B
        LD B, #8
rn_l:   CALL rng_step
        DEC B
        JNZ rn_l
        POP B
        LD A, [RNG]
        RET

rng_step:
        LD A, [RNG+1]
        SHR A
        ST A, [RNG+1]
        LD A, [RNG]
        ROR A
        ST A, [RNG]
        JNC rs_end
        LD A, [RNG+1]
        XOR A, #$B4
        ST A, [RNG+1]
rs_end: RET
