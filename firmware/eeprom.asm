; Open8-VGA firmware — SAVE / LOAD of the editor text on the 25LC512 SPI EEPROM
; Author: Adham Elshafei
;
; SPI is bit-banged: OUT_PORT bit 0 = SCK, bit 1 = MOSI, bit 2 = /CS; IN_PORT bit 0
; = MISO (pulled up: reads 1 when no EEPROM is fitted). Mode 0, MSB first.
; The 64 KiB EEPROM holds 4 slots of 16 KiB. A slot: "O8", length (2 bytes, low
; first), then the text. Writes go in 128-byte pages; every save is read back and
; compared before it is reported as saved.

EE_SCK      = 1
EE_MOSI     = 2
EE_CS       = 4
EE_MAXLEN   = 16380         ; 16384 - 4 header bytes

EE_MODE     = $FCB0         ; 0 = save, 1 = load
EE_SLOT     = $FCB1
EE_ADDR     = $FCB2         ; 2
EE_CNT      = $FCB4         ; 2
EE_LEN      = $FCB6         ; 2
EE_OPEN     = $FCB8         ; a write page is open
EE_IN       = $FCB9
EE_TMP      = $FCBA
EE_HDR      = $FCBC         ; 4: "O8", length
EE_USED     = $FCC0         ; 4 flags: slot holds a program
EE_POST     = $FCC4         ; 16: " bytes, slot N." built in RAM

; ---------------------------------------------------------------- SPI
ee_select:
        LD A, #0                ; /CS low, SCK low
        ST A, [OUT_PORT]
        RET

ee_deselect:
        LD A, #EE_CS
        ST A, [OUT_PORT]
        RET

; send A, return the byte received in A. Preserves B and X.
spi_byte:
        PUSH B
        ST A, [EE_TMP]
        LD B, #8
sb_l:   LD A, [EE_TMP]          ; next bit -> C
        SHL A
        ST A, [EE_TMP]
        LD A, #0
        JNC sb_0
        LD A, #EE_MOSI
sb_0:   ST A, [OUT_PORT]        ; SCK low: data out
        OR A, #EE_SCK
        ST A, [OUT_PORT]        ; SCK high: both sides sample
        LD A, [IN_PORT]
        SHR A                   ; MISO -> C
        LD A, [EE_IN]
        ROL A
        ST A, [EE_IN]
        DEC B
        JNZ sb_l
        LD A, #0
        ST A, [OUT_PORT]
        LD A, [EE_IN]
        POP B
        RET

; read the status register -> A
ee_status:
        CALL ee_select
        LD A, #$05
        CALL spi_byte
        LD A, #0
        CALL spi_byte
        PUSH A
        CALL ee_deselect
        POP A
        RET

; wait until no write cycle is running. C = 1 if no EEPROM answers.
ee_wait:
        PUSH B
        LD B, #0
ew_l:   CALL ee_status
        CMP A, #$FF             ; status $FF: nothing on the bus
        JZ ew_fail
        AND A, #1
        JZ ew_ok
        DEC B
        JNZ ew_l
ew_fail:
        POP B
        SEC
        RET
ew_ok:  POP B
        CLC
        RET

; start reading at EE_ADDR (leaves the chip selected)
ee_read_at:
        CALL ee_select
        LD A, #$03
        CALL spi_byte
        LD A, [EE_ADDR+1]
        CALL spi_byte
        LD A, [EE_ADDR]
        JMP spi_byte

; slot EE_SLOT -> EE_ADDR = slot * $4000 + A
ee_slot_addr:
        ST A, [EE_ADDR]
        LD A, [EE_SLOT]
        SHL A
        SHL A
        SHL A
        SHL A
        SHL A
        SHL A
        ST A, [EE_ADDR+1]
        RET

; read the header of slot EE_SLOT into EE_HDR. C = 1 if the slot holds no program.
ee_read_header:
        LD A, #0
        CALL ee_slot_addr
        CALL ee_read_at
        LD X, #EE_HDR
        LD B, #4
rh_l:   LD A, #0
        CALL spi_byte
        ST A, [X+]
        DEC B
        JNZ rh_l
        CALL ee_deselect
        LD A, [EE_HDR]
        CMP A, #'O'
        JNZ rh_no
        LD A, [EE_HDR+1]
        CMP A, #'8'
        JNZ rh_no
        LD A, [EE_HDR+2]        ; length <= EE_MAXLEN
        ST A, [EE_LEN]
        SUB A, #<EE_MAXLEN + 1
        LD A, [EE_HDR+3]
        ST A, [EE_LEN+1]
        SBC A, #>EE_MAXLEN
        JNC rh_no
        CLC
        RET
rh_no:  SEC
        RET

; ---------------------------------------------------------------- page writes
; write byte A at EE_ADDR (opens 128-byte pages as needed). C = 1 on error.
ee_put:
        ST A, [EE_TMP+1]
        LD A, [EE_OPEN]
        CMP A, #0
        JNZ ep_send
        CALL ee_wait            ; open a page: WREN, then WRITE address
        JC ep_ret
        CALL ee_select
        LD A, #$06
        CALL spi_byte
        CALL ee_deselect
        CALL ee_select
        LD A, #$02
        CALL spi_byte
        LD A, [EE_ADDR+1]
        CALL spi_byte
        LD A, [EE_ADDR]
        CALL spi_byte
        LD A, #1
        ST A, [EE_OPEN]
ep_send:
        LD A, [EE_TMP+1]
        CALL spi_byte
        LD A, [EE_ADDR]
        INC A
        ST A, [EE_ADDR]
        JNZ ep_nc
        LD A, [EE_ADDR+1]
        INC A
        ST A, [EE_ADDR+1]
        LD A, #0
ep_nc:  AND A, #$7F             ; page boundary: close the page (write cycle starts)
        JNZ ep_ok
ee_close:
        LD A, [EE_OPEN]
        CMP A, #0
        JZ ep_ok
        CALL ee_deselect
        LD A, #0
        ST A, [EE_OPEN]
ep_ok:  CLC
ep_ret: RET

; write EE_CNT bytes from X. C = 1 on error.
ee_put_bytes:
        LD A, [EE_CNT]
        OR A, [EE_CNT+1]
        JZ ep_ok
        LD A, [X+]
        PUSH X
        CALL ee_put
        POP X
        JC ep_ret
        LD A, [EE_CNT]
        DEC A
        ST A, [EE_CNT]
        JNC ee_put_bytes
        LD A, [EE_CNT+1]
        DEC A
        ST A, [EE_CNT+1]
        JMP ee_put_bytes

; compare EE_CNT bytes from X with the chip's data stream. C = 1 if different.
ee_verify_bytes:
        LD A, [EE_CNT]
        OR A, [EE_CNT+1]
        JZ ep_ok
        LD A, #0
        CALL spi_byte
        CMP A, [X]
        JNZ vb_bad
        INC X
        LD A, [EE_CNT]
        DEC A
        ST A, [EE_CNT]
        JNC ee_verify_bytes
        LD A, [EE_CNT+1]
        DEC A
        ST A, [EE_CNT+1]
        JMP ee_verify_bytes
vb_bad: SEC
        RET

; ---------------------------------------------------------------- save / load
; save the editor text to slot EE_SLOT. Sets the editor message.
ee_save:
        LD A, [GAP_S]           ; text must be in one piece: move the gap to the end
        ST A, [CUR_SAVE]
        LD A, [GAP_S+1]
        ST A, [CUR_SAVE+1]
        CALL ed_to_end
        LD A, [GAP_S]           ; length = GAP_S - BUF_START
        ST A, [EE_LEN]
        ST A, [EE_HDR+2]
        LD A, [GAP_S+1]
        SUB A, #>BUF_START
        ST A, [EE_LEN+1]
        ST A, [EE_HDR+3]
        LD A, #'O'
        ST A, [EE_HDR]
        LD A, #'8'
        ST A, [EE_HDR+1]
        LD A, [EE_LEN]          ; too long for a slot?
        SUB A, #<EE_MAXLEN + 1
        LD A, [EE_LEN+1]
        SBC A, #>EE_MAXLEN
        JNC es_long
        LD A, #0
        ST A, [EE_OPEN]
        CALL ee_slot_addr
        LD X, #EE_HDR           ; header, then the text
        LD A, #4
        ST A, [EE_CNT]
        LD A, #0
        ST A, [EE_CNT+1]
        CALL ee_put_bytes
        JC es_fail
        CALL ee_len_to_cnt
        LD X, #BUF_START
        CALL ee_put_bytes
        JC es_fail
        CALL ee_close
        CALL ee_wait
        JC es_fail
        LD A, #0                ; read it all back
        CALL ee_slot_addr
        CALL ee_read_at
        LD X, #EE_HDR
        LD A, #4
        ST A, [EE_CNT]
        LD A, #0
        ST A, [EE_CNT+1]
        CALL ee_verify_bytes
        JC es_verify
        CALL ee_len_to_cnt
        LD X, #BUF_START
        CALL ee_verify_bytes
        JC es_verify
        CALL ee_deselect
        LD X, #s_saved
        CALL ee_msg_len
        JMP ee_restore_cursor
es_long:
        LD X, #s_ee_long
        CALL set_msg
        JMP ee_restore_cursor
es_verify:
        CALL ee_deselect
es_fail:
        CALL ee_close
        LD X, #s_ee_fail
        CALL set_msg
ee_restore_cursor:
        LD A, [CUR_SAVE]
        ST A, [P0]
        LD A, [CUR_SAVE+1]
        ST A, [P0+1]
        JMP ed_back_to

ee_len_to_cnt:
        LD A, [EE_LEN]
        ST A, [EE_CNT]
        LD A, [EE_LEN+1]
        ST A, [EE_CNT+1]
        RET

; message X + EE_LEN + " bytes, slot N"
ee_msg_len:
        CALL set_msg
        LD A, #1
        ST A, [MSG_KIND]
        LD A, [EE_LEN]
        ST A, [MSG_NUM]
        LD A, [EE_LEN+1]
        ST A, [MSG_NUM+1]
        LD X, #s_bytes_slot     ; copy " bytes, slot " to RAM, add the digit
        LD B, #0
mp_l:   LD A, [X+]
        CMP A, #0
        JZ mp_d
        PUSH X
        LD X, #EE_POST
        PUSH A
        MOV A, B
        ADD X, A
        POP A
        ST A, [X]
        POP X
        INC B
        JMP mp_l
mp_d:   LD X, #EE_POST
        MOV A, B
        ADD X, A
        LD A, [EE_SLOT]
        ADD A, #'1'
        ST A, [X+]
        LD A, #'.'
        ST A, [X+]
        LD A, #0
        ST A, [X]
        LD A, #<EE_POST
        ST A, [MSG_POST]
        LD A, #>EE_POST
        ST A, [MSG_POST+1]
        RET

; load slot EE_SLOT into the editor (header already checked by ee_read_header)
ee_load:
        CALL ed_new
        LD A, #<BUF_END         ; GAP_E = BUF_END - length: cursor at the top
        SUB A, [EE_LEN]
        ST A, [GAP_E]
        LD A, #>BUF_END
        SBC A, [EE_LEN+1]
        ST A, [GAP_E+1]
        LD A, #4
        CALL ee_slot_addr
        CALL ee_read_at
        LD A, [GAP_E]
        MOV XL, A
        LD A, [GAP_E+1]
        MOV XH, A
        CALL ee_len_to_cnt
el3_l:  LD A, [EE_CNT]
        OR A, [EE_CNT+1]
        JZ el3_end
        LD A, #0
        CALL spi_byte
        ST A, [X+]
        LD A, [EE_CNT]
        DEC A
        ST A, [EE_CNT]
        JNC el3_l
        LD A, [EE_CNT+1]
        DEC A
        ST A, [EE_CNT+1]
        JMP el3_l
el3_end:
        CALL ee_deselect
        LD X, #s_loaded
        JMP ee_msg_len

; ---------------------------------------------------------------- the slot screen
; A = 0 save, 1 load. Shows the 4 slots, asks for one, does the work.
ee_menu:
        ST A, [EE_MODE]
        LD A, #0
        ST A, [CON_ATTR]
        CALL r_cls
        LD A, #$80
        ST A, [CON_ATTR]
        LD B, #0
        CALL clear_row
        LD X, #s_ee_save_t
        LD A, [EE_MODE]
        CMP A, #0
        JZ em2_t
        LD X, #s_ee_load_t
em2_t:  CALL r_print
        LD A, #0
        ST A, [CON_ATTR]
        CALL ee_deselect
        CALL ee_wait
        JNC em2_ok
        LD X, #s_ee_none
        JMP set_msg
em2_ok: LD A, #0
        LD B, #3
        CALL r_gotoxy
        LD A, #0
        ST A, [EE_SLOT]
em2_l:  LD X, #s_indent
        CALL r_print
        LD A, [EE_SLOT]
        ADD A, #'1'
        CALL r_putc
        LD X, #s_dot
        CALL r_print
        LD X, #EE_USED
        LD A, [EE_SLOT]
        ADD X, A
        LD A, #0
        ST A, [X]
        CALL ee_read_header
        JC em2_empty
        LD X, #EE_USED
        LD A, [EE_SLOT]
        ADD X, A
        LD A, #1
        ST A, [X]
        LD A, #4                ; show the first line of the text (up to 50 characters)
        CALL ee_slot_addr
        CALL ee_read_at
        LD B, #50               ; at most 50 characters, and no more than the length
        LD A, [EE_LEN+1]
        CMP A, #0
        JNZ em2_c
        LD A, [EE_LEN]
        CMP A, #50
        JNC em2_c
        MOV B, A
        CMP A, #0
        JZ em2_cd
em2_c:  LD A, #0
        CALL spi_byte
        CMP A, #10
        JZ em2_cd
        CMP A, #9
        JNZ em2_cp
        LD A, #' '
em2_cp: CALL r_putc
        DEC B
        JNZ em2_c
em2_cd: CALL ee_deselect
        LD X, #s_lparen
        CALL r_print
        LD A, [EE_LEN]
        MOV XL, A
        LD A, [EE_LEN+1]
        MOV XH, A
        CALL r_prdec16
        LD X, #s_bytes_rp
        CALL r_print
        JMP em2_next
em2_empty:
        LD X, #s_empty
        CALL r_print
em2_next:
        CALL r_newline
        CALL r_newline
        LD A, [EE_SLOT]
        INC A
        ST A, [EE_SLOT]
        CMP A, #4
        JNZ em2_l
        LD X, #s_ee_prompt
        CALL r_print
em2_k:  CALL r_getkey
        CMP A, #KEY_ESC
        JZ em2_end
        SUB A, #'1'
        CMP A, #4
        JNC em2_k
        ST A, [EE_SLOT]
        LD X, #EE_USED
        ADD X, A
        LD A, [EE_MODE]
        CMP A, #0
        JNZ em2_load
        LD A, [X]               ; save: confirm before overwriting a program
        CMP A, #0
        JZ em2_save
        CALL r_newline
        LD X, #s_ee_overwrite
        CALL r_print
        CALL r_getkey
        AND A, #$DF
        CMP A, #'Y'
        JNZ em2_end
em2_save:
        CALL r_newline
        LD X, #s_ee_saving
        CALL r_print
        JMP ee_save
em2_load:
        LD A, [X]
        CMP A, #0
        JNZ em2_ld2
        LD X, #s_ee_empty
        JMP set_msg
em2_ld2:
        CALL r_newline
        LD X, #s_confirm_load
        CALL r_print
        CALL r_getkey
        AND A, #$DF
        CMP A, #'Y'
        JNZ em2_end
        CALL ee_read_header
        JMP ee_load
em2_end:
        RET
