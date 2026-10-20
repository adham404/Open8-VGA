; Open8-VGA firmware — full-screen editor
; Author: Adham Elshafei
;
; Text is kept in a gap buffer: [BUF_START, GAP_S) is the text before the cursor,
; [GAP_E, BUF_END) the text after it; the gap in between is free space. Typing and
; deleting at the cursor cost the same anywhere in a 16 KiB file. Lines end with LF.
;
; Screen: row 0 status bar, rows 1-27 text, row 28 messages, row 29 key help.

PREV_LINE   = $FC90         ; 2
KEY         = $FC92
MSG_POST    = $FC93         ; 2
MSG_KIND    = $FC95         ; 0 none, 1 = decimal MSG_NUM, 2 = hex MSG_NUM
MSG_NUM     = $FC96         ; 2
CUR_ROW     = $FC98
CUR_SCOL    = $FC99
LINE_ROW    = $FC9A
LCOL        = $FC9B

; ================================================================ buffer primitives
ed_new:
        LD A, #<BUF_START
        ST A, [GAP_S]
        ST A, [TOP]
        LD A, #>BUF_START
        ST A, [GAP_S+1]
        ST A, [TOP+1]
        LD A, #<BUF_END
        ST A, [GAP_E]
        LD A, #>BUF_END
        ST A, [GAP_E+1]
        LD A, #1
        ST A, [CUR_LINE]
        ST A, [TOP_LINE]
        LD A, #0
        ST A, [CUR_LINE+1]
        ST A, [TOP_LINE+1]
        ST A, [WANT_COL]
        ST A, [ASM_OK]
        LD A, #'O'
        ST A, [MAGIC]
        LD A, #'8'
        ST A, [MAGIC+1]
        RET

; C = 1 if P0 < P1 (unsigned 16-bit)
lt16:
        LD A, [P0]
        SUB A, [P1]
        LD A, [P0+1]
        SBC A, [P1+1]
        RET

; Check the buffer pointers after a warm reset. C = 1 if they are not sane.
ed_check_ptrs:
        LD X, #chk_pairs
        LD A, #5
        ST A, [T3]
cp_l:   LD A, [T3]              ; each pair: address of P0 source, address of P1 source
        CMP A, #0
        JZ cp_ok
        DEC A
        ST A, [T3]
        CALL cp_load
        ST A, [P0]
        MOV A, B
        ST A, [P0+1]
        CALL cp_load
        ST A, [P1]
        MOV A, B
        ST A, [P1+1]
        PUSH X
        CALL lt16
        POP X
        JC cp_bad
        JMP cp_l
cp_ok:  CLC
        RET
cp_bad: SEC
        RET
; X -> .dw address of a 16-bit variable; returns A = low, B = high, X advanced
cp_load:
        LD A, [X+]
        ST A, [P2]
        LD A, [X+]
        ST A, [P2+1]
        PUSH X
        LD A, [P2]
        MOV XL, A
        LD A, [P2+1]
        MOV XH, A
        LD A, [X+]
        LD B, [X]
        POP X
        RET
c_bufstart: .dw BUF_START
c_bufend:   .dw BUF_END
chk_pairs:                      ; "P0 < P1 is an error" for each pair
        .dw GAP_S, c_bufstart
        .dw GAP_E, GAP_S
        .dw c_bufend, GAP_E
        .dw GAP_S, TOP
        .dw TOP, c_bufstart

; Recount CUR_LINE and TOP_LINE from the buffer (after a warm reset).
ed_recount:
        LD X, #BUF_START
        LD A, #1
        ST A, [CUR_LINE]
        ST A, [TOP_LINE]
        LD A, #0
        ST A, [CUR_LINE+1]
        ST A, [TOP_LINE+1]
rc_l:   MOV A, XL               ; reached TOP? then TOP_LINE = lines so far
        CMP A, [TOP]
        JNZ rc_nt
        MOV A, XH
        CMP A, [TOP+1]
        JNZ rc_nt
        LD A, [CUR_LINE]
        ST A, [TOP_LINE]
        LD A, [CUR_LINE+1]
        ST A, [TOP_LINE+1]
rc_nt:  MOV A, XL
        CMP A, [GAP_S]
        JNZ rc_go
        MOV A, XH
        CMP A, [GAP_S+1]
        JZ rc_end
rc_go:  LD A, [X+]
        CMP A, #10
        JNZ rc_l
        CALL inc_line
        JMP rc_l
rc_end: RET

inc_line:
        LD A, [CUR_LINE]
        INC A
        ST A, [CUR_LINE]
        JNZ il_e
        LD A, [CUR_LINE+1]
        INC A
        ST A, [CUR_LINE+1]
il_e:   RET

dec_line:
        LD A, [CUR_LINE]
        DEC A
        ST A, [CUR_LINE]
        JNC dl_e
        LD A, [CUR_LINE+1]
        DEC A
        ST A, [CUR_LINE+1]
dl_e:   RET

; C = 1 if the cursor is at the start of the buffer
at_start:
        LD A, [GAP_S+1]
        CMP A, #>BUF_START
        JNZ as_no
        LD A, [GAP_S]
        CMP A, #<BUF_START
        JNZ as_no
        SEC
        RET
as_no:  CLC
        RET

; C = 1 if the cursor is at the end of the buffer
at_end:
        LD A, [GAP_E+1]
        CMP A, #>BUF_END
        JNZ ae_no
        LD A, [GAP_E]
        CMP A, #<BUF_END
        JNZ ae_no
        SEC
        RET
ae_no:  CLC
        RET

; Move the cursor one character left / right. C = 1 if impossible.
ed_left:
        CALL at_start
        JC el_end
        LD A, [GAP_S]
        MOV XL, A
        LD A, [GAP_S+1]
        MOV XH, A
        DEC X
        MOV A, XL
        ST A, [GAP_S]
        MOV A, XH
        ST A, [GAP_S+1]
        LD B, [X]
        LD A, [GAP_E]
        MOV XL, A
        LD A, [GAP_E+1]
        MOV XH, A
        DEC X
        MOV A, XL
        ST A, [GAP_E]
        MOV A, XH
        ST A, [GAP_E+1]
        ST B, [X]
        MOV A, B
        CMP A, #10
        JNZ el_ok
        CALL dec_line
el_ok:  CLC
el_end: RET

ed_right:
        CALL at_end
        JC er_end
        LD A, [GAP_E]
        MOV XL, A
        LD A, [GAP_E+1]
        MOV XH, A
        LD B, [X+]
        MOV A, XL
        ST A, [GAP_E]
        MOV A, XH
        ST A, [GAP_E+1]
        LD A, [GAP_S]
        MOV XL, A
        LD A, [GAP_S+1]
        MOV XH, A
        ST B, [X+]
        MOV A, XL
        ST A, [GAP_S]
        MOV A, XH
        ST A, [GAP_S+1]
        MOV A, B
        CMP A, #10
        JNZ er_ok
        CALL inc_line
er_ok:  CLC
er_end: RET

; Insert character A at the cursor. C = 1 if the buffer is full.
ed_insert:
        ST A, [T2]
        LD A, [GAP_E]
        SUB A, [GAP_S]
        ST A, [T0]
        LD A, [GAP_E+1]
        SBC A, [GAP_S+1]
        JNZ ei_ok
        LD A, [T0]
        CMP A, #2               ; always keep one free byte (assembler end marker)
        JNC ei_ok
        SEC
        RET
ei_ok:  LD A, [GAP_S]
        MOV XL, A
        LD A, [GAP_S+1]
        MOV XH, A
        LD A, [T2]
        ST A, [X+]
        MOV A, XL
        ST A, [GAP_S]
        MOV A, XH
        ST A, [GAP_S+1]
        LD A, [T2]
        CMP A, #10
        JNZ ei_d
        CALL inc_line
ei_d:   CLC
        RET

; Delete the character before / after the cursor; T2 = deleted char. C = 1 if none.
ed_backspace:
        CALL at_start
        JC eb_end
        LD A, [GAP_S]
        MOV XL, A
        LD A, [GAP_S+1]
        MOV XH, A
        DEC X
        MOV A, XL
        ST A, [GAP_S]
        MOV A, XH
        ST A, [GAP_S+1]
        LD A, [X]
        ST A, [T2]
        CMP A, #10
        JNZ eb_ok
        CALL dec_line
eb_ok:  CLC
eb_end: RET

ed_delete:
        CALL at_end
        JC ed_del_end
        LD A, [GAP_E]
        MOV XL, A
        LD A, [GAP_E+1]
        MOV XH, A
        LD A, [X+]
        ST A, [T2]
        MOV A, XL
        ST A, [GAP_E]
        MOV A, XH
        ST A, [GAP_E+1]
        CLC
ed_del_end:
        RET

; A = CUR_COL = column of the cursor (0-255)
ed_col:
        LD A, [GAP_S]
        MOV XL, A
        LD A, [GAP_S+1]
        MOV XH, A
        LD B, #0
ec_l:   MOV A, XH
        CMP A, #>BUF_START
        JNZ ec_c
        MOV A, XL
        CMP A, #<BUF_START
        JZ ec_end
ec_c:   DEC X
        LD A, [X]
        CMP A, #10
        JZ ec_end
        INC B
        JZ ec_max
        JMP ec_l
ec_max: LD B, #255
ec_end: MOV A, B
        ST A, [CUR_COL]
        RET

; character after the cursor -> A (0 at the end of the buffer)
ed_peek:
        CALL at_end
        JC ep_end
        LD A, [GAP_E]
        MOV XL, A
        LD A, [GAP_E+1]
        MOV XH, A
        LD A, [X]
        RET
ep_end: LD A, #0
        RET

ed_home:
        CALL ed_col
        ST A, [CNT]
eh_l:   LD A, [CNT]
        CMP A, #0
        JZ eh_end
        DEC A
        ST A, [CNT]
        CALL ed_left
        JMP eh_l
eh_end: RET

ed_endl:
        CALL ed_peek
        CMP A, #10
        JZ en_end
        CMP A, #0
        JZ en_end
        CALL ed_right
        JMP ed_endl
en_end: RET

; move right up to WANT_COL characters, stopping at the end of the line
ed_tocol:
        LD A, [WANT_COL]
        ST A, [CNT]
et_l:   LD A, [CNT]
        CMP A, #0
        JZ et_end
        CALL ed_peek
        CMP A, #10
        JZ et_end
        CMP A, #0
        JZ et_end
        CALL ed_right
        LD A, [CNT]
        DEC A
        ST A, [CNT]
        JMP et_l
et_end: RET

ed_up:
        CALL ed_home
        CALL ed_left
        JC eu_end
        CALL ed_home
        CALL ed_tocol
eu_end: RET

ed_down:
        CALL ed_endl
        CALL ed_right
        JC ed_dn_end
        CALL ed_tocol
ed_dn_end:
        RET

; move the gap so that GAP_S = P0 (P0 must be at or before the cursor)
ed_back_to:
        LD A, [GAP_S]
        CMP A, [P0]
        JNZ bt_go
        LD A, [GAP_S+1]
        CMP A, [P0+1]
        JZ bt_end
bt_go:  CALL ed_left
        JNC ed_back_to
bt_end: RET

ed_to_end:
        CALL ed_right
        JNC ed_to_end
        RET

; ================================================================ screen
; Make sure the cursor line is visible (adjust TOP / TOP_LINE).
ensure_top:
        LD A, [CUR_LINE]
        ST A, [P0]
        LD A, [CUR_LINE+1]
        ST A, [P0+1]
        LD A, [TOP_LINE]
        ST A, [P1]
        LD A, [TOP_LINE+1]
        ST A, [P1+1]
        CALL lt16
        JC et_above
        ; diff = CUR_LINE - TOP_LINE; if diff >= TEXT_ROWS move the top down
        LD A, [CUR_LINE]
        SUB A, [TOP_LINE]
        ST A, [T0]
        LD A, [CUR_LINE+1]
        SBC A, [TOP_LINE+1]
        JNZ et_below
        LD A, [T0]
        CMP A, #TEXT_ROWS
        JNC et_below
        RET
et_above:                       ; top = start of the cursor line
        CALL cur_line_start
        LD A, [LINE_START]
        ST A, [TOP]
        LD A, [LINE_START+1]
        ST A, [TOP+1]
        LD A, [CUR_LINE]
        ST A, [TOP_LINE]
        LD A, [CUR_LINE+1]
        ST A, [TOP_LINE+1]
        RET
et_below:                       ; top = TEXT_ROWS-1 lines above the cursor line
        CALL cur_line_start
        LD A, [LINE_START]
        MOV XL, A
        LD A, [LINE_START+1]
        MOV XH, A
        LD A, [CUR_LINE]
        ST A, [TOP_LINE]
        LD A, [CUR_LINE+1]
        ST A, [TOP_LINE+1]
        LD B, #TEXT_ROWS - 1
eb_l:   MOV A, XH               ; at buffer start? stop
        CMP A, #>BUF_START
        JNZ eb_c
        MOV A, XL
        CMP A, #<BUF_START
        JZ eb_set
eb_c:   DEC X                   ; X -> LF ending the previous line
eb_s:   MOV A, XH
        CMP A, #>BUF_START
        JNZ eb_s2
        MOV A, XL
        CMP A, #<BUF_START
        JZ eb_dec
eb_s2:  DEC X
        LD A, [X]
        CMP A, #10
        JNZ eb_s
        INC X
eb_dec: LD A, [TOP_LINE]
        DEC A
        ST A, [TOP_LINE]
        JNC eb_nb
        LD A, [TOP_LINE+1]
        DEC A
        ST A, [TOP_LINE+1]
eb_nb:  DEC B
        JNZ eb_l
eb_set: MOV A, XL
        ST A, [TOP]
        MOV A, XH
        ST A, [TOP+1]
        RET

; LINE_START = address of the first character of the cursor line
cur_line_start:
        CALL ed_col
        LD A, [GAP_S]
        SUB A, [CUR_COL]
        ST A, [LINE_START]
        LD A, [GAP_S+1]
        SBC A, #0
        ST A, [LINE_START+1]
        RET

; Draw one text line. X = source pointer, LINE_ROW = screen row.
; Returns X at the start of the next line (or at BUF_END).
render_line:
        PUSH X
        LD A, #0
        ST A, [LCOL]
        ST A, [CON_SCRY]
        LD B, [LINE_ROW]
        CALL vaddr
        MOV A, XL
        ST A, [VP]
        MOV A, XH
        ST A, [VP+1]
        POP X
rl_l:   MOV A, XL               ; reached the cursor (gap)?
        CMP A, [GAP_S]
        JNZ rl_ng
        MOV A, XH
        CMP A, [GAP_S+1]
        JNZ rl_ng
        LD A, [LINE_ROW]
        ST A, [CUR_ROW]
        LD A, [LCOL]
        CMP A, #80
        JC rl_cc
        LD A, #79
rl_cc:  ST A, [CUR_SCOL]
        LD A, #1
        ST A, [CUR_FOUND]
        LD A, [GAP_E]
        MOV XL, A
        LD A, [GAP_E+1]
        MOV XH, A
rl_ng:  MOV A, XH               ; end of text?
        CMP A, #>BUF_END
        JZ rl_pad
        LD B, [X+]
        MOV A, B
        CMP A, #10
        JZ rl_pad
        CMP A, #9
        JZ rl_tab
        CALL rl_put
        JMP rl_l
rl_tab: LD B, #' '              ; tab: spaces up to the next multiple of 8
        CALL rl_put
rl_t2:  LD A, [LCOL]
        AND A, #7
        JZ rl_l
        CALL rl_put
        JMP rl_t2
rl_pad: PUSH X
        LD A, [VP]
        MOV XL, A
        LD A, [VP+1]
        MOV XH, A
        LD B, #' '
rl_p:   LD A, [LCOL]
        CMP A, #80
        JNC rl_done
        ST B, [X+]
        INC A
        ST A, [LCOL]
        JMP rl_p
rl_done:
        POP X
        RET

; put character B at the next screen column (nothing beyond column 80). Keeps B, X.
rl_put: LD A, [LCOL]
        CMP A, #80
        JNC rp_end
        INC A
        ST A, [LCOL]
        PUSH X
        LD A, [VP]
        MOV XL, A
        LD A, [VP+1]
        MOV XH, A
        ST B, [X+]
        MOV A, XL
        ST A, [VP]
        MOV A, XH
        ST A, [VP+1]
        POP X
rp_end: RET

render_all:
        CALL ensure_top
        LD A, #0
        ST A, [CUR_FOUND]
        LD A, [TOP]
        MOV XL, A
        LD A, [TOP+1]
        MOV XH, A
        LD A, #TEXT_ROW0
        ST A, [LINE_ROW]
ra_l:   CALL render_line
        LD A, [LINE_ROW]
        INC A
        ST A, [LINE_ROW]
        CMP A, #TEXT_ROW0 + TEXT_ROWS
        JNZ ra_l
        JMP draw_cursor

; redraw only the cursor line (cursor and top line unchanged)
render_cur:
        LD A, #0
        ST A, [CUR_FOUND]
        CALL cur_line_start
        LD A, [CUR_LINE]
        SUB A, [TOP_LINE]
        ADD A, #TEXT_ROW0
        ST A, [LINE_ROW]
        LD A, [LINE_START]
        MOV XL, A
        LD A, [LINE_START+1]
        MOV XH, A
        CALL render_line
draw_cursor:
        LD A, [CUR_FOUND]
        CMP A, #0
        JZ dc_end
        LD A, [CUR_SCOL]
        LD B, [CUR_ROW]
        CALL vaddr
        LD A, [X]
        XOR A, #$80
        ST A, [X]
dc_end: RET

draw_status:
        LD A, #$80
        ST A, [CON_ATTR]
        LD B, #0
        CALL clear_row
        LD X, #s_title
        CALL r_print
        LD A, #40
        ST A, [CON_X]
        LD X, #s_line
        CALL r_print
        LD A, [CUR_LINE]
        MOV XL, A
        LD A, [CUR_LINE+1]
        MOV XH, A
        CALL r_prdec16
        LD X, #s_col
        CALL r_print
        CALL ed_col
        INC A
        CALL r_prdec
        LD X, #s_free
        CALL r_print
        LD A, [GAP_E]           ; free = GAP_E - GAP_S - 1
        SUB A, [GAP_S]
        MOV XL, A
        LD A, [GAP_E+1]
        SBC A, [GAP_S+1]
        MOV XH, A
        DEC X
        CALL r_prdec16
        LD A, #0
        ST A, [CON_ATTR]
        RET

draw_bar:
        LD A, #$80
        ST A, [CON_ATTR]
        LD B, #BAR_ROW
        CALL clear_row
        LD X, #s_bar
        CALL r_print
        LD A, #0
        ST A, [CON_ATTR]
        RET

draw_msg:
        LD B, #MSG_ROW
        CALL clear_row
        LD A, [MSG_PTR]
        OR A, [MSG_PTR+1]
        JZ dm_num
        LD A, [MSG_PTR]
        MOV XL, A
        LD A, [MSG_PTR+1]
        MOV XH, A
        CALL r_print
dm_num: LD A, [MSG_KIND]
        CMP A, #1
        JZ dm_dec
        CMP A, #2
        JNZ dm_post
        LD A, #'$'
        CALL r_putc
        LD A, [MSG_NUM+1]
        CALL r_prhex
        LD A, [MSG_NUM]
        CALL r_prhex
        JMP dm_post
dm_dec: LD A, [MSG_NUM]
        MOV XL, A
        LD A, [MSG_NUM+1]
        MOV XH, A
        CALL r_prdec16
dm_post:
        LD A, [MSG_POST]
        OR A, [MSG_POST+1]
        JZ dm_end
        LD A, [MSG_POST]
        MOV XL, A
        LD A, [MSG_POST+1]
        MOV XH, A
        CALL r_print
dm_end: RET

; X = message string (simple message, no number)
set_msg:
        MOV A, XL
        ST A, [MSG_PTR]
        MOV A, XH
        ST A, [MSG_PTR+1]
        LD A, #0
        ST A, [MSG_KIND]
        ST A, [MSG_POST]
        ST A, [MSG_POST+1]
        RET

clear_msg:
        LD X, #0
        JMP set_msg

; ================================================================ main loop
ed_enter:
        LD SP, #0
        LD A, #0
        ST A, [CON_ATTR]
        CALL r_cls
        CALL draw_bar
        LD A, #1
        ST A, [REDRAW]
ed_loop:
        LD A, [REDRAW]
        CMP A, #0
        JZ ed_part
        CALL render_all
        JMP ed_drawn
ed_part:
        CALL render_cur
ed_drawn:
        CALL draw_status
        CALL draw_msg
ed_wait:
        CALL rng_step
        CALL r_keyhit
        CMP A, #0
        JZ ed_wait
        ST A, [KEY]
        LD A, [CUR_LINE]
        ST A, [PREV_LINE]
        LD A, [CUR_LINE+1]
        ST A, [PREV_LINE+1]
        CALL clear_msg
        LD A, #0
        ST A, [REDRAW]
        CALL ed_key
        LD A, [CUR_LINE]        ; line changed -> full redraw
        CMP A, [PREV_LINE]
        JNZ ed_full
        LD A, [CUR_LINE+1]
        CMP A, [PREV_LINE+1]
        JZ ed_loop
ed_full:
        LD A, #1
        ST A, [REDRAW]
        JMP ed_loop

; handle the key in KEY
ed_key:
        LD A, [KEY]
        CMP A, #' '
        JC ek_ctl
        CMP A, #127
        JNC ek_special
        ; printable character
        CALL ed_col
        CMP A, #79
        JNC ek_long
        LD A, [KEY]
        CALL ed_insert
        JC ek_full
        JMP set_want
ek_long:
        LD X, #s_long
        JMP set_msg
ek_full:
        LD X, #s_full
        JMP set_msg
ek_ctl: CMP A, #KEY_ENTER
        JZ ek_enter
        CMP A, #KEY_BS
        JZ ek_bs
        CMP A, #KEY_TAB
        JZ ek_tab
        RET
ek_enter:
        LD A, #10
        CALL ed_insert
        JC ek_full
        JMP set_want
ek_bs:  CALL ed_backspace
        JC ek_r
        LD A, [T2]
        CMP A, #10
        JNZ set_want
        LD A, #1
        ST A, [REDRAW]
        JMP set_want
ek_tab: CALL ed_col             ; a TAB character, shown as spaces to column 8n
        CMP A, #79
        JNC ek_r
        LD A, #9
        CALL ed_insert
        JC ek_full
        JMP set_want
ek_special:
        CMP A, #K_LEFT
        JZ ek_left
        CMP A, #K_RIGHT
        JZ ek_right
        CMP A, #K_UP
        JZ ed_up
        CMP A, #K_DOWN
        JZ ed_down
        CMP A, #K_HOME
        JZ ek_home
        CMP A, #K_END
        JZ ek_end
        CMP A, #K_PGUP
        JZ ek_pgup
        CMP A, #K_PGDN
        JZ ek_pgdn
        CMP A, #K_DEL
        JZ ek_del
        CMP A, #K_F1
        JZ ek_help
        CMP A, #K_F2
        JZ ek_asm
        CMP A, #K_F3
        JZ ek_run
        CMP A, #K_F4
        JZ ek_save
        CMP A, #K_F5
        JZ ek_examples
        CMP A, #K_F6
        JZ ek_load
        CMP A, #K_F9
        JZ ek_new
ek_r:   RET
ek_left:
        CALL ed_left
        JMP set_want
ek_right:
        CALL ed_right
        JMP set_want
ek_home:
        CALL ed_home
        JMP set_want
ek_end: CALL ed_endl
        JMP set_want
ek_del: CALL ed_delete
        JC ek_r
        LD A, [T2]
        CMP A, #10
        JNZ set_want
        LD A, #1
        ST A, [REDRAW]
        JMP set_want
ek_pgup:
        LD A, #TEXT_ROWS - 1
        ST A, [T3]
pu_l:   CALL ed_up
        LD A, [T3]
        DEC A
        ST A, [T3]
        JNZ pu_l
        RET
ek_pgdn:
        LD A, #TEXT_ROWS - 1
        ST A, [T3]
pd_l:   CALL ed_down
        LD A, [T3]
        DEC A
        ST A, [T3]
        JNZ pd_l
        RET
set_want:
        CALL ed_col
        ST A, [WANT_COL]
        RET

ek_help:
        CALL help_view
        JMP ed_enter

ek_new: LD X, #s_confirm_new
        CALL ask_yes
        JNC ek_r
        CALL ed_new
        LD A, #1
        ST A, [REDRAW]
        RET

ek_examples:
        CALL examples_menu
        JMP ed_enter

ek_save:
        LD A, #0
        CALL ee_menu
        JMP ed_enter

ek_load:
        LD A, #1
        CALL ee_menu
        JMP ed_enter

ek_asm: CALL ed_assemble
        LD A, #1
        ST A, [REDRAW]
        RET

ek_run: CALL ed_assemble
        LD A, #1
        ST A, [REDRAW]
        LD A, [ASM_OK]
        CMP A, #0
        JZ ek_r
        ; ---- run the user program
        LD A, #0
        ST A, [CON_ATTR]
        CALL r_cls
        ST A, [SYS_STATUS]      ; clear the write-violation latch
        LD SP, #0
        CALL USER_START
; returning here (RET from the program, or CALL EXIT) ends the run
r_exit:
        LD SP, #0
        LD A, #0
        ST A, [CON_ATTR]
        LD A, [CON_X]
        CMP A, #0
        JZ rx_nl
        CALL r_newline
rx_nl:  LD A, [SYS_STATUS]
        AND A, #4
        JZ rx_ok
        LD X, #s_violation
        CALL r_print
rx_ok:  LD X, #s_finished
        CALL r_print
        CALL r_getkey
        JMP ed_enter

; X = question; shows it on the message row and waits for Y or N. C = 1 for yes.
ask_yes:
        CALL set_msg
        CALL draw_msg
ay_l:   CALL r_keyhit
        CMP A, #0
        JZ ay_l
        PUSH A
        CALL clear_msg
        POP A
        CMP A, #'y'
        JZ ay_yes
        CMP A, #'Y'
        JZ ay_yes
        CLC
        RET
ay_yes: SEC
        RET

; ---------------------------------------------------------------- assemble
; Assemble the whole buffer to $8000. Sets ASM_OK and an editor message.
; On error the cursor moves to the start of the offending line.
ed_assemble:
        LD A, #0
        ST A, [ASM_OK]
        LD A, [GAP_S]
        ST A, [CUR_SAVE]
        LD A, [GAP_S+1]
        ST A, [CUR_SAVE+1]
        LD X, #s_assembling
        CALL set_msg
        CALL draw_msg
        CALL ed_to_end
        LD A, [GAP_S]           ; terminate the text (the gap always has a free byte)
        MOV XL, A
        ST A, [A_END]
        LD A, [GAP_S+1]
        MOV XH, A
        ST A, [A_END+1]
        LD A, #0
        ST A, [X]
        CALL asm_main
        JC ea_err
        LD A, #1
        ST A, [ASM_OK]
        LD A, [CUR_SAVE]
        ST A, [P0]
        LD A, [CUR_SAVE+1]
        ST A, [P0+1]
        CALL ed_back_to
        LD X, #s_asm_ok
        CALL set_msg
        LD A, #1
        ST A, [MSG_KIND]
        LD A, [A_PC]            ; size = A_PC - $8000
        ST A, [MSG_NUM]
        LD A, [A_PC+1]
        SUB A, #>USER_START
        ST A, [MSG_NUM+1]
        LD A, #<s_asm_ok2
        ST A, [MSG_POST]
        LD A, #>s_asm_ok2
        ST A, [MSG_POST+1]
        RET
ea_err: LD A, [A_LSTART]
        ST A, [P0]
        LD A, [A_LSTART+1]
        ST A, [P0+1]
        CALL ed_back_to
        LD X, #s_err_line
        CALL set_msg
        LD A, #1
        ST A, [MSG_KIND]
        LD A, [A_LINE]
        ST A, [MSG_NUM]
        LD A, [A_LINE+1]
        ST A, [MSG_NUM+1]
        LD A, [A_ERR]           ; MSG_POST = err_table[A_ERR]
        SHL A
        LD X, #err_table
        ADD X, A
        LD A, [X+]
        ST A, [MSG_POST]
        LD A, [X]
        ST A, [MSG_POST+1]
        RET
