; Open8-VGA firmware — help viewer and example loader
; Author: Adham Elshafei
;
; Help text: flash pages BANK_HELP.. ; byte 0 = number of pages, then pages of
; text separated by form feeds (12), terminated by 0.
; Examples: page BANK_EXDIR holds: count, then per example a zero-terminated
; name and the flash page where its text starts. Each text is zero-terminated.

HP_COUNT    = $FCA0

help_view:
        LD A, #0
        ST A, [HELP_PAGE]
        LD A, #BANK_HELP
        CALL bopen
        CALL bget
        ST A, [HP_COUNT]
hv_show:
        LD A, #0
        ST A, [CON_ATTR]
        CALL r_cls
        LD A, #$80
        ST A, [CON_ATTR]
        LD B, #0
        CALL clear_row
        LD X, #s_help_title
        CALL r_print
        LD A, [HELP_PAGE]
        INC A
        CALL r_prdec
        LD A, #'/'
        CALL r_putc
        LD A, [HP_COUNT]
        CALL r_prdec
        LD X, #s_help_keys
        CALL r_print
        LD A, #0
        ST A, [CON_ATTR]
        ; find the page: skip HELP_PAGE form feeds after the count byte
        LD A, #BANK_HELP
        CALL bopen
        CALL bget
        LD A, [HELP_PAGE]
        ST A, [T3]
hv_skip:
        LD A, [T3]
        CMP A, #0
        JZ hv_print
hv_s2:  CALL bget
        CMP A, #0
        JZ hv_keys
        CMP A, #12
        JNZ hv_s2
        LD A, [T3]
        DEC A
        ST A, [T3]
        JMP hv_skip
hv_print:
        LD A, #0
        LD B, #1
        CALL r_gotoxy
hv_p:   CALL bget
        CMP A, #0
        JZ hv_keys
        CMP A, #12
        JZ hv_keys
        CALL r_putc
        LD A, [CON_Y]           ; never print into the last row
        CMP A, #29
        JNZ hv_p
hv_keys:
        CALL r_keyhit
        CMP A, #0
        JZ hv_keys
        CMP A, #KEY_ESC
        JZ hv_end
        CMP A, #K_F1
        JZ hv_end
        CMP A, #K_PGUP
        JZ hv_prev
        CMP A, #K_LEFT
        JZ hv_prev
        CMP A, #K_UP
        JZ hv_prev
        CMP A, #KEY_BS
        JZ hv_prev
        ; any other key: next page
        LD A, [HELP_PAGE]
        INC A
        CMP A, [HP_COUNT]
        JNC hv_keys
        ST A, [HELP_PAGE]
        JMP hv_show
hv_prev:
        LD A, [HELP_PAGE]
        CMP A, #0
        JZ hv_keys
        DEC A
        ST A, [HELP_PAGE]
        JMP hv_show
hv_end: RET

; ---------------------------------------------------------------- examples
examples_menu:
        LD A, #0
        ST A, [CON_ATTR]
        CALL r_cls
        LD A, #$80
        ST A, [CON_ATTR]
        LD B, #0
        CALL clear_row
        LD X, #s_ex_title
        CALL r_print
        LD A, #0
        ST A, [CON_ATTR]
        LD A, #0
        LD B, #2
        CALL r_gotoxy
        LD A, #BANK_EXDIR
        CALL bopen
        CALL bget
        ST A, [HP_COUNT]
        LD A, #0
        ST A, [T3]
em_l:   LD A, [T3]
        CMP A, [HP_COUNT]
        JZ em_ask
        LD X, #s_indent
        CALL r_print
        LD A, [T3]
        ADD A, #'1'
        CALL r_putc
        LD X, #s_dot
        CALL r_print
em_n:   CALL bget
        CMP A, #0
        JZ em_nd
        CALL r_putc
        JMP em_n
em_nd:  CALL bget               ; page number (unused here)
        CALL r_newline
        LD A, [T3]
        INC A
        ST A, [T3]
        JMP em_l
em_ask: CALL r_newline
        LD X, #s_ex_prompt
        CALL r_print
em_k:   CALL r_getkey
        CMP A, #KEY_ESC
        JZ em_end
        SUB A, #'1'
        CMP A, [HP_COUNT]
        JNC em_k
        PUSH A
        LD X, #s_confirm_load
        CALL r_newline
        CALL r_print
        CALL r_getkey
        AND A, #$DF
        CMP A, #'Y'
        POP A
        JNZ em_end
        CALL ex_load
em_end: RET

; Load example A into the editor (replaces the text). The text is placed at the
; end of the buffer so the cursor starts at the top.
ex_load:
        ST A, [T3]
        LD A, #BANK_EXDIR       ; find its page
        CALL bopen
        CALL bget
el2_rec:
        CALL bget               ; skip the name
        CMP A, #0
        JNZ el2_rec
        CALL bget
        ST A, [T2]
        LD A, [T3]
        CMP A, #0
        JZ el2_found
        DEC A
        ST A, [T3]
        JMP el2_rec
el2_found:
        CALL ed_new
        LD A, [T2]              ; pass 1: length -> CNT
        CALL bopen
        LD A, #0
        ST A, [CNT]
        ST A, [CNT+1]
el2_len:
        CALL bget
        CMP A, #0
        JZ el2_copy
        LD A, [CNT]
        INC A
        ST A, [CNT]
        JNZ el2_len
        LD A, [CNT+1]
        INC A
        ST A, [CNT+1]
        JMP el2_len
el2_copy:                       ; GAP_E = BUF_END - length
        LD A, #<BUF_END
        SUB A, [CNT]
        ST A, [GAP_E]
        MOV XL, A
        LD A, #>BUF_END
        SBC A, [CNT+1]
        ST A, [GAP_E+1]
        MOV XH, A
        LD A, [T2]
        CALL bopen
el2_c:  CALL bget
        CMP A, #0
        JZ el2_done
        ST A, [X+]
        JMP el2_c
el2_done:
        LD A, #1
        ST A, [REDRAW]
        RET
