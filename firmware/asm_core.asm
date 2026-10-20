; Open8-VGA firmware — on-board two-pass assembler
; Author: Adham Elshafei
;
; Reads the editor text [BUF_START, A_END) (zero-terminated) and writes machine
; code to $8000-$AEFF. Pass 1 collects labels, pass 2 emits bytes; nothing is
; written to user memory unless pass 1 succeeded.
;
; Supported: every instruction form, labels, NAME = expr, .db .dw .ds .org,
; numbers 42 $2A 0x2A %101 0b101 'c', expressions with + - < > and $.
; Names: up to 14 characters. Symbols: 192 (hash table at $F000).
;
; Fast name comparison: IDBUF and MNBUF live in the stack page; comparisons set
; SP to point at them and use POP to fetch their bytes, so X is free to walk
; the other string. No CALL/PUSH happens while SP is redirected.
;
; Errors: C = 1 on return, A_ERR = code, A_LINE / A_LSTART = offending line.

E_UNKNOWN   = 1
E_OPERANDS  = 2
E_UNDEFINED = 3
E_DUPLICATE = 4
E_RANGE     = 5
E_TOOBIG    = 6
E_SYMFULL   = 7
E_SYNTAX    = 8
E_NUMBER    = 9
E_LONGNAME  = 10
E_DIRECTIVE = 11
E_FORWARD   = 12
E_RESERVED  = 13

KIND_IMM    = 7
KIND_ABS    = 8
KIND_IND    = 9
KIND_INDINC = 10
KIND_ADDR   = 11

; ================================================================ driver
asm_main:
        LD A, #BANK_ASMTAB
        ST A, [ROM_BANK]
        CALL sym_clear
        LD A, #1
        ST A, [A_PASS]
am_pass:
        LD A, #<USER_START
        ST A, [A_PC]
        LD A, #>USER_START
        ST A, [A_PC+1]
        LD A, #1
        ST A, [A_LINE]
        LD A, #0
        ST A, [A_LINE+1]
        LD X, #BUF_START
am_line:
        LD A, [X]
        CMP A, #0
        JZ am_done
        MOV A, XL
        ST A, [A_LSTART]
        MOV A, XH
        ST A, [A_LSTART+1]
        CALL asm_line           ; X = line start in, X = end of line out
        JC am_err
am_eol: LD A, [X]               ; skip anything left up to the end of the line
        CMP A, #0
        JZ am_done
        INC X
        CMP A, #10
        JNZ am_eol
        LD A, [A_LINE]
        INC A
        ST A, [A_LINE]
        JNZ am_line
        LD A, [A_LINE+1]
        INC A
        ST A, [A_LINE+1]
        JMP am_line
am_done:
        LD A, [A_PASS]
        CMP A, #2
        JZ am_ok
        LD A, #2
        ST A, [A_PASS]
        JMP am_pass
am_ok:  CLC
        RET
am_err: SEC
        RET

; error exit used everywhere: A = code
fail:   ST A, [A_ERR]
        SEC
        RET

; ================================================================ one line
asm_line:
        LD A, [A_PC]
        ST A, [A_LPC]
        LD A, [A_PC+1]
        ST A, [A_LPC+1]
        CALL skip_sp
        CALL is_end
        JC al_ok
        CALL is_idstart
        JNC al_syntax
        CALL read_ident
        JC al_ret
        LD A, [X]
        CMP A, #':'
        JNZ al_noLabel
        INC X                   ; ---- label
        CALL check_reserved
        JC al_ret
        LD A, [A_PC]
        ST A, [A_VAL]
        LD A, [A_PC+1]
        ST A, [A_VAL+1]
        CALL sym_define
        JC al_ret
        CALL skip_sp
        CALL is_end
        JC al_ok
        CALL is_idstart
        JNC al_syntax
        CALL read_ident
        JC al_ret
        JMP al_stmt
al_noLabel:
        MOV A, XL
        ST A, [A_SAVEX]
        MOV A, XH
        ST A, [A_SAVEX+1]
        CALL skip_sp
        CMP A, #'='
        JNZ al_restore
        INC X                   ; ---- NAME = expr
        CALL save_id
        CALL eval_expr
        JC al_ret
        CALL restore_id
        CALL sym_define
        JC al_ret
        JMP expect_end
al_restore:
        LD A, [A_SAVEX]
        MOV XL, A
        LD A, [A_SAVEX+1]
        MOV XH, A
al_stmt:
        LD A, [IDBUF]
        CMP A, #'.'
        JZ directive
        JMP instruction
al_ok:  CLC
al_ret: RET
al_syntax:
        LD A, #E_SYNTAX
        JMP fail

; after a statement only blanks and a comment may follow
expect_end:
        CALL skip_sp
        CALL is_end
        JC al_ok
        LD A, #E_SYNTAX
        JMP fail

; ================================================================ instructions
instruction:
        LD A, [A_IDLEN]         ; mnemonic -> MNBUF (5 chars, space padded)
        CMP A, #6
        JNC in_unknown
        CALL make_mnbuf
        CALL apply_alias
        CALL parse_operands
        JC al_ret
        CALL find_instr         ; A_REC -> record, or error
        JC al_ret
        PUSH X
        LD A, [A_REC]
        MOV XL, A
        LD A, [A_REC+1]
        MOV XH, A
        LD A, #6
        ADD X, A
        LD A, [X+]
        ST A, [A_NBYTES]
        LD A, [X]               ; opcode
        POP X
        CALL emit
        JC al_ret
        LD A, [A_NBYTES]
        CMP A, #0
        JZ expect_end
        CMP A, #1
        JNZ in_two
        LD A, [A_OPV]
        ST A, [A_VAL]
        LD A, [A_OPV+1]
        ST A, [A_VAL+1]
        CALL check_byte
        JC al_ret
        LD A, [A_OPV]
        CALL emit
        JC al_ret
        JMP expect_end
in_two: LD A, [A_OPV]
        CALL emit
        JC al_ret
        LD A, [A_OPV+1]
        CALL emit
        JC al_ret
        JMP expect_end
in_unknown:
        LD A, #E_UNKNOWN
        JMP fail

; IDBUF -> MNBUF (5 bytes, zeros become spaces)
make_mnbuf:
        PUSH X
        LD X, #IDBUF
mm_l:   LD A, [X]
        CMP A, #0
        JNZ mm_c
        LD A, #' '
mm_c:   PUSH A
        MOV A, XL
        OR A, #MNBUF_STK
        MOV XL, A
        POP A
        ST A, [X]
        MOV A, XL
        AND A, #$1F
        INC A
        MOV XL, A
        CMP A, #5
        JNZ mm_l
        POP X
        RET

; replace alias mnemonics (JEQ -> JZ ...) using alias_tab: 5-byte alias, 5-byte target
apply_alias:
        PUSH X
        LD X, #alias_tab
aa_l:   LD A, [X]
        CMP A, #0
        JZ aa_end
        CALL cmp_mn
        JZ aa_hit
        LD A, #10
        ADD X, A
        JMP aa_l
aa_hit: LD A, #5
        ADD X, A
        LD A, #MNBUF_STK        ; copy 5 bytes to MNBUF
        ST A, [T0]
aa_c:   LD B, [X+]
        PUSH X
        LD A, [T0]
        MOV XL, A
        LD A, #>MNBUF
        MOV XH, A
        ST B, [X]
        LD A, [T0]
        INC A
        ST A, [T0]
        POP X
        CMP A, #MNBUF_STK + 5
        JNZ aa_c
aa_end: POP X
        RET

; Z = 1 if the 5 bytes at X equal MNBUF. X is not changed.
cmp_mn:
        PUSH X
        MOV A, SP
        ST A, [SAVE_SP]
        LD SP, #MNBUF_STK
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cm_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cm_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cm_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cm_out
        POP B
        LD A, [X+]
        CMP A, B
cm_out: LD A, [SAVE_SP]
        MOV SP, A
        POP X
        RET

; search the instruction table for MNBUF + (A_K1, A_K2). A_REC = record.
find_instr:
        PUSH X
        LD A, #0
        ST A, [A_MNFOUND]
        LD A, [A_K2]            ; key = K1 | K2 << 4
        SHL A
        SHL A
        SHL A
        SHL A
        OR A, [A_K1]
        ST A, [T0]
        LD X, #isa_tab
fi2_l:  LD A, [X]
        CMP A, #0
        JZ fi2_none
        CALL cmp_mn
        JNZ fi2_next
        LD A, #1
        ST A, [A_MNFOUND]
        PUSH X
        LD A, #5
        ADD X, A
        LD A, [X]
        POP X
        CMP A, [T0]
        JZ fi2_hit
fi2_next:
        LD A, #8
        ADD X, A
        JMP fi2_l
fi2_hit:
        MOV A, XL
        ST A, [A_REC]
        MOV A, XH
        ST A, [A_REC+1]
        POP X
        CLC
        RET
fi2_none:
        POP X
        LD A, [A_MNFOUND]
        CMP A, #0
        JZ in_unknown
        LD A, #E_OPERANDS
        JMP fail

; ---------------------------------------------------------------- operands
parse_operands:
        LD A, #0
        ST A, [A_K1]
        ST A, [A_K2]
        CALL skip_sp
        CALL is_end
        JC po_ok
        CALL parse_operand
        JC po_ret
        LD A, [A_KIND]
        ST A, [A_K1]
        CALL skip_sp
        CMP A, #','
        JNZ po_ok
        INC X
        CALL skip_sp
        CALL parse_operand
        JC po_ret
        LD A, [A_KIND]
        ST A, [A_K2]
po_ok:  CLC
po_ret: RET

; one operand at X -> A_KIND (and A_OPV for value operands)
parse_operand:
        LD A, [X]
        CMP A, #'#'
        JZ op_imm
        CMP A, #'['
        JZ op_mem
        CALL is_idstart
        JNC op_expr
        MOV A, XL               ; maybe a register name
        ST A, [A_SAVEX]
        MOV A, XH
        ST A, [A_SAVEX+1]
        CALL read_ident
        JC po_ret
        CALL reg_kind
        CMP A, #0
        JZ op_restore
        ST A, [A_KIND]
        CLC
        RET
op_restore:
        LD A, [A_SAVEX]
        MOV XL, A
        LD A, [A_SAVEX+1]
        MOV XH, A
op_expr:
        LD A, #KIND_ADDR
op_val: ST A, [A_KIND]
        CALL eval_expr
        JC po_ret
        LD A, [A_VAL]
        ST A, [A_OPV]
        LD A, [A_VAL+1]
        ST A, [A_OPV+1]
        CLC
        RET
op_imm: INC X
        LD A, #KIND_IMM
        JMP op_val
op_mem: INC X
        CALL skip_sp
        MOV A, XL
        ST A, [A_SAVEX]
        MOV A, XH
        ST A, [A_SAVEX+1]
        LD A, [X]
        CALL is_idstart
        JNC om_expr
        CALL read_ident
        JC po_ret
        CALL reg_kind
        CMP A, #3               ; X ?
        JNZ om_restore
        CALL skip_sp
        CMP A, #']'
        JZ om_ind
        CMP A, #'+'
        JNZ om_syntax
        INC X
        CALL skip_sp
        CMP A, #']'
        JNZ om_syntax
        INC X
        LD A, #KIND_INDINC
        ST A, [A_KIND]
        CLC
        RET
om_ind: INC X
        LD A, #KIND_IND
        ST A, [A_KIND]
        CLC
        RET
om_restore:
        LD A, [A_SAVEX]
        MOV XL, A
        LD A, [A_SAVEX+1]
        MOV XH, A
om_expr:
        LD A, #KIND_ABS
        ST A, [A_KIND]
        CALL eval_expr
        JC po_ret
        LD A, [A_VAL]
        ST A, [A_OPV]
        LD A, [A_VAL+1]
        ST A, [A_OPV+1]
        CALL skip_sp
        CMP A, #']'
        JNZ om_syntax
        INC X
        CLC
        RET
om_syntax:
        LD A, #E_SYNTAX
        JMP fail

; IDBUF -> A = register kind (1 A, 2 B, 3 X, 4 SP, 5 XL, 6 XH) or 0
reg_kind:
        LD A, [IDBUF+2]
        CMP A, #0
        JNZ rk_no
        LD A, [IDBUF+1]
        CMP A, #0
        JNZ rk_two
        LD A, [IDBUF]
        CMP A, #'A'
        JZ rk_a
        CMP A, #'B'
        JZ rk_b
        CMP A, #'X'
        JZ rk_x
rk_no:  LD A, #0
        RET
rk_a:   LD A, #1
        RET
rk_b:   LD A, #2
        RET
rk_x:   LD A, #3
        RET
rk_two: LD A, [IDBUF]
        CMP A, #'S'
        JZ rk_s
        CMP A, #'X'
        JNZ rk_no
        LD A, [IDBUF+1]
        CMP A, #'L'
        JZ rk_xl
        CMP A, #'H'
        JNZ rk_no
        LD A, #6
        RET
rk_xl:  LD A, #5
        RET
rk_s:   LD A, [IDBUF+1]
        CMP A, #'P'
        JNZ rk_no
        LD A, #4
        RET

; labels may not be register names or mnemonics. C = 1 (error set) if reserved.
check_reserved:
        CALL reg_kind
        CMP A, #0
        JNZ cr_bad
        LD A, [A_IDLEN]
        CMP A, #6
        JNC cr_ok
        CALL make_mnbuf
        PUSH X
        LD X, #isa_tab
cr_l:   LD A, [X]
        CMP A, #0
        JZ cr_ok2
        CALL cmp_mn
        JZ cr_bad2
        LD A, #8
        ADD X, A
        JMP cr_l
cr_ok2: POP X
cr_ok:  CLC
        RET
cr_bad2:
        POP X
cr_bad: LD A, #E_RESERVED
        JMP fail

; ================================================================ directives
directive:
        PUSH X
        LD X, #dir_tab
dr_l:   LD A, [X]
        CMP A, #0
        JZ dr_unknown
        PUSH X
        CALL cmp_name
        POP X
        JZ dr_hit
        LD A, #NAME_MAX + 1
        ADD X, A
        JMP dr_l
dr_hit: LD A, #NAME_MAX
        ADD X, A
        LD A, [X]
        POP X
        CMP A, #1
        JZ d_db
        CMP A, #2
        JZ d_dw
        CMP A, #3
        JZ d_ds
        JMP d_org
dr_unknown:
        POP X
        LD A, #E_DIRECTIVE
        JMP fail

d_db:   CALL skip_sp
        CMP A, #'"'
        JZ db_str
        CALL eval_expr
        JC al_ret
        CALL check_byte
        JC al_ret
        LD A, [A_VAL]
        CALL emit
        JC al_ret
db_next:
        CALL skip_sp
        CMP A, #','
        JNZ expect_end
        INC X
        JMP d_db
db_str: INC X
db_s:   LD A, [X]
        CMP A, #'"'
        JZ db_send
        CALL is_end_strict
        JC db_bad
        INC X
        CMP A, #'\\'
        JNZ db_put
        LD A, [X+]
        CMP A, #'n'
        JNZ db_e1
        LD A, #10
        JMP db_put
db_e1:  CMP A, #'t'
        JNZ db_e2
        LD A, #9
        JMP db_put
db_e2:  CMP A, #'0'
        JNZ db_put              ; \\ and \" give the character itself
        LD A, #0
db_put: CALL emit
        JC al_ret
        JMP db_s
db_send:
        INC X
        JMP db_next
db_bad: LD A, #E_SYNTAX
        JMP fail

d_dw:   CALL eval_expr
        JC al_ret
        LD A, [A_VAL]
        CALL emit
        JC al_ret
        LD A, [A_VAL+1]
        CALL emit
        JC al_ret
        CALL skip_sp
        CMP A, #','
        JNZ expect_end
        INC X
        JMP d_dw

d_ds:   CALL eval_defined
        JC al_ret
        LD A, [A_VAL]
        ST A, [A_COUNT]
        LD A, [A_VAL+1]
        ST A, [A_COUNT+1]
        LD A, #0
        ST A, [A_FILL]
        CALL skip_sp
        CMP A, #','
        JNZ ds_go
        INC X
        CALL eval_defined
        JC al_ret
        LD A, [A_VAL]
        ST A, [A_FILL]
ds_go:  LD A, [A_COUNT]
        OR A, [A_COUNT+1]
        JZ expect_end
        LD A, [A_FILL]
        CALL emit
        JC al_ret
        LD A, [A_COUNT]
        DEC A
        ST A, [A_COUNT]
        JNC ds_go
        LD A, [A_COUNT+1]
        DEC A
        ST A, [A_COUNT+1]
        JMP ds_go

d_org:  CALL eval_defined
        JC al_ret
        LD A, [A_VAL]
        ST A, [A_PC]
        LD A, [A_VAL+1]
        ST A, [A_PC+1]
        JMP expect_end

; expression whose value must be known in pass 1
eval_defined:
        CALL eval_expr
        JC ed2_ret
        LD A, [A_UNDEF]
        CMP A, #0
        JZ ed2_ok
        LD A, #E_FORWARD
        JMP fail
ed2_ok: CLC
ed2_ret:
        RET

; ================================================================ output
; emit byte A at A_PC (written in pass 2 only); A_PC must stay in $8000-$AEFF
emit:
        ST A, [T1]
        LD A, [A_PC+1]
        CMP A, #>USER_START
        JC em_big
        CMP A, #>USER_LIMIT
        JNC em_big
        LD A, [A_PASS]
        CMP A, #2
        JNZ em_inc
        PUSH X
        LD A, [A_PC]
        MOV XL, A
        LD A, [A_PC+1]
        MOV XH, A
        LD A, [T1]
        ST A, [X]
        POP X
em_inc: LD A, [A_PC]
        INC A
        ST A, [A_PC]
        JNZ em_ok
        LD A, [A_PC+1]
        INC A
        ST A, [A_PC+1]
em_ok:  CLC
        RET
em_big: LD A, #E_TOOBIG
        JMP fail

; A_VAL must fit in a byte (-128..255); checked in pass 2 only
check_byte:
        LD A, [A_PASS]
        CMP A, #2
        JNZ cb_ok
        LD A, [A_VAL+1]
        CMP A, #0
        JZ cb_ok
        CMP A, #$FF
        JNZ cb_bad
        LD A, [A_VAL]
        CMP A, #$80
        JC cb_bad
cb_ok:  CLC
        RET
cb_bad: LD A, #E_RANGE
        JMP fail

; ================================================================ expressions
; X -> expression. A_VAL = value; A_UNDEF = 1 if it used an undefined symbol (pass 1).
eval_expr:
        LD A, #0
        ST A, [A_VAL]
        ST A, [A_VAL+1]
        ST A, [A_UNDEF]
        LD A, #'+'
        ST A, [A_OP]
        CALL skip_sp
        CMP A, #'-'
        JNZ ee_term
        ST A, [A_OP]
        INC X
ee_term:
        LD A, [A_OP]            ; eval_term may recurse into nothing that uses A_OP
        PUSH A
        CALL eval_term
        POP B
        JC ee_ret
        MOV A, B
        CMP A, #'-'
        JZ ee_sub
        LD A, [A_VAL]
        ADD A, [A_TERM]
        ST A, [A_VAL]
        LD A, [A_VAL+1]
        ADC A, [A_TERM+1]
        ST A, [A_VAL+1]
        JMP ee_more
ee_sub: LD A, [A_VAL]
        SUB A, [A_TERM]
        ST A, [A_VAL]
        LD A, [A_VAL+1]
        SBC A, [A_TERM+1]
        ST A, [A_VAL+1]
ee_more:
        CALL skip_sp
        CMP A, #'+'
        JZ ee_op
        CMP A, #'-'
        JZ ee_op
        CLC
ee_ret: RET
ee_op:  ST A, [A_OP]
        INC X
        JMP ee_term

; one term -> A_TERM
eval_term:
        CALL skip_sp
        LD A, #0
        ST A, [A_PREFIX]
        ST A, [A_TERM]
        ST A, [A_TERM+1]
        LD A, [X]
        CMP A, #'<'
        JZ et_pre
        CMP A, #'>'
        JNZ et_prim
et_pre: ST A, [A_PREFIX]
        INC X
        CALL skip_sp
et_prim:
        LD A, [X]
        CMP A, #'$'
        JZ et_dollar
        CMP A, #'%'
        JZ et_bin
        CMP A, #39              ; '
        JZ et_char
        CMP A, #'0'
        JC et_notdig
        CMP A, #'9' + 1
        JC et_digit
et_notdig:
        CALL is_idstart
        JC et_sym
        LD A, #E_SYNTAX
        JMP fail
et_digit:
        CMP A, #'0'
        JNZ et_dec
        INC X                   ; 0x... / 0b...
        LD A, [X]
        CMP A, #'x'
        JZ et_hex
        CMP A, #'X'
        JZ et_hex
        CMP A, #'b'
        JZ et_0b
        CMP A, #'B'
        JZ et_0b
        DEC X
        JMP et_dec
et_0b:  INC X                   ; only binary if a 0/1 follows
        LD A, [X]
        DEC X
        CMP A, #'0'
        JZ et_bin
        CMP A, #'1'
        JZ et_bin
        DEC X
        JMP et_dec
et_dollar:
        INC X
        LD A, [X]
        CALL hex_val
        JNC et_hexdig
        LD A, [A_LPC]           ; $ alone = address of this line
        ST A, [A_TERM]
        LD A, [A_LPC+1]
        ST A, [A_TERM+1]
        JMP et_apply
et_hex: INC X
et_hexdig:
        LD A, #0
        ST A, [A_DIGIT]
eh2_l:  LD A, [X]
        CALL hex_val
        JC et_numend
        ST A, [T0]
        LD B, #4
eh2_s:  CALL term_shl
        DEC B
        JNZ eh2_s
        LD A, [A_TERM]
        OR A, [T0]
        ST A, [A_TERM]
        LD A, #1
        ST A, [A_DIGIT]
        INC X
        JMP eh2_l
et_bin: INC X
        LD A, #0
        ST A, [A_DIGIT]
eb2_l:  LD A, [X]
        SUB A, #'0'
        CMP A, #2
        JNC et_numend
        ST A, [T0]
        CALL term_shl
        LD A, [A_TERM]
        OR A, [T0]
        ST A, [A_TERM]
        LD A, #1
        ST A, [A_DIGIT]
        INC X
        JMP eb2_l
et_dec: LD A, #0
        ST A, [A_DIGIT]
ed3_l:  LD A, [X]
        SUB A, #'0'
        CMP A, #10
        JNC et_numend
        ST A, [T0]
        CALL term_mul10
        LD A, [A_TERM]
        ADD A, [T0]
        ST A, [A_TERM]
        LD A, [A_TERM+1]
        ADC A, #0
        ST A, [A_TERM+1]
        LD A, #1
        ST A, [A_DIGIT]
        INC X
        JMP ed3_l
et_numend:                      ; need a digit, and no letters glued to the number
        LD A, [A_DIGIT]
        CMP A, #0
        JZ et_badnum
        LD A, [X]
        CALL is_idchar
        JC et_badnum
        JMP et_apply
et_badnum:
        LD A, #E_NUMBER
        JMP fail
et_char:
        INC X
        LD A, [X+]
        CMP A, #92              ; backslash escapes
        JNZ ec_plain
        LD A, [X+]
        CMP A, #'n'
        JNZ ec_t
        LD A, #10
        JMP ec_plain
ec_t:   CMP A, #'t'
        JNZ ec_0
        LD A, #9
        JMP ec_plain
ec_0:   CMP A, #'0'
        JNZ ec_plain
        LD A, #0
ec_plain:
        ST A, [A_TERM]
        LD A, [X]
        CMP A, #39
        JNZ et_badnum
        INC X
        JMP et_apply
et_sym: CALL read_ident
        JC et_ret
        CALL sym_value
        JNC et_apply
        LD A, [A_PASS]
        CMP A, #2
        JZ et_undef
        LD A, #1
        ST A, [A_UNDEF]
et_apply:
        LD A, [A_PREFIX]
        CMP A, #'<'
        JZ et_lo
        CMP A, #'>'
        JNZ et_done
        LD A, [A_TERM+1]
        ST A, [A_TERM]
et_lo:  LD A, #0
        ST A, [A_TERM+1]
et_done:
        CLC
et_ret: RET
et_undef:
        LD A, #E_UNDEFINED
        JMP fail

term_shl:
        LD A, [A_TERM]
        SHL A
        ST A, [A_TERM]
        LD A, [A_TERM+1]
        ROL A
        ST A, [A_TERM+1]
        RET

; A_TERM *= 10  (x*2 + x*8)
term_mul10:
        CALL term_shl
        LD A, [A_TERM]
        ST A, [P2]
        LD A, [A_TERM+1]
        ST A, [P2+1]
        CALL term_shl
        CALL term_shl
        LD A, [A_TERM]
        ADD A, [P2]
        ST A, [A_TERM]
        LD A, [A_TERM+1]
        ADC A, [P2+1]
        ST A, [A_TERM+1]
        RET

; A = character -> A = hex digit value, C = 1 if not a hex digit
hex_val:
        CMP A, #'0'
        JC hv_no
        CMP A, #'9' + 1
        JC hv_dig
        AND A, #$DF             ; upper case
        CMP A, #'A'
        JC hv_no
        CMP A, #'F' + 1
        JNC hv_no
        SUB A, #'A' - 10
        CLC
        RET
hv_dig: SUB A, #'0'
        CLC
        RET
hv_no:  SEC
        RET

; ================================================================ lexical helpers
; skip blanks; A = current character (not consumed)
skip_sp:
        LD A, [X]
        CMP A, #' '
        JZ ss_n
        CMP A, #9
        JZ ss_n
        RET
ss_n:   INC X
        JMP skip_sp

; C = 1 if [X] ends the statement (0, LF, ';', CR)
is_end:
        LD A, [X]
is_end_a:
        CMP A, #0
        JZ ie_yes
        CMP A, #10
        JZ ie_yes
        CMP A, #13
        JZ ie_yes
        CMP A, #';'
        JZ ie_yes
        CLC
        RET
ie_yes: SEC
        RET

; C = 1 if A ends the line (0, LF) - used inside strings, where ';' is text
is_end_strict:
        CMP A, #0
        JZ ie_yes
        CMP A, #10
        JZ ie_yes
        CLC
        RET

; C = 1 if A can start a name: letter, '_' or '.'
is_idstart:
        CMP A, #'_'
        JZ ii_yes
        CMP A, #'.'
        JZ ii_yes
        JMP is_alpha
ii_yes: SEC
        RET

; C = 1 if A can continue a name
is_idchar:
        CMP A, #'0'
        JC is_idstart
        CMP A, #'9' + 1
        JC ii_yes
        JMP is_idstart

; Read a name at X into IDBUF (upper case, zero padded). C = 1 if too long.
read_ident:
        PUSH X
        LD X, #IDBUF
        LD A, #0
        LD B, #21
ri_clr: ST A, [X+]
        DEC B
        JNZ ri_clr
        POP X
        LD B, #0
ri_l:   LD A, [X]
        CALL is_idchar
        JNC ri_end
        LD A, [X+]
        CMP A, #'a'
        JC ri_up
        CMP A, #'z' + 1
        JNC ri_up
        SUB A, #32
ri_up:  ST A, [T0]
        MOV A, B
        CMP A, #NAME_MAX
        JNC ri_long
        PUSH X
        MOV XL, A               ; IDBUF is at $AF00: address = $AF00 + index
        LD A, #>IDBUF
        MOV XH, A
        LD A, [T0]
        ST A, [X]
        POP X
        INC B
        JMP ri_l
ri_end: MOV A, B
        ST A, [A_IDLEN]
        CLC
        RET
ri_long:
        LD A, #E_LONGNAME
        JMP fail

; copy IDBUF <-> LBLBUF (both in the stack page)
save_id:
        PUSH X
        LD B, #0
sv_l:   MOV A, B
        MOV XL, A
        LD A, #>IDBUF
        MOV XH, A
        LD A, [X]
        PUSH A
        MOV A, XL
        OR A, #<LBLBUF
        MOV XL, A
        POP A
        ST A, [X]
        INC B
        MOV A, B
        CMP A, #21
        JNZ sv_l
        POP X
        RET

restore_id:
        PUSH X
        LD B, #0
rs2_l:  MOV A, B
        OR A, #<LBLBUF
        MOV XL, A
        LD A, #>IDBUF
        MOV XH, A
        LD A, [X]
        PUSH A
        MOV A, B
        MOV XL, A
        POP A
        ST A, [X]
        INC B
        MOV A, B
        CMP A, #21
        JNZ rs2_l
        POP X
        RET

; ================================================================ symbol table
sym_clear:
        LD X, #SYMTAB
        LD A, #0
sc_l:   ST A, [X+]
        ST A, [X+]
        ST A, [X+]
        ST A, [X+]
        MOV B, A
        MOV A, XH
        CMP A, #>(SYMTAB + SYM_SLOTS * SYM_SIZE)
        MOV A, B
        JNZ sc_l
        RET

; Z = 1 if the 14-byte name at X equals IDBUF. X is advanced, not restored.
cmp_name:
        MOV A, SP
        ST A, [SAVE_SP]
        LD SP, #IDBUF_STK
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
        JNZ cn_out
        POP B
        LD A, [X+]
        CMP A, B
cn_out: LD A, [SAVE_SP]
        MOV SP, A
        RET

; hash of IDBUF -> A_HASH (0-191): byte sum mod 192
sym_hash:
        PUSH X
        LD X, #IDBUF
        LD A, #0
        LD B, #NAME_MAX
sh_l:   ADD A, [X]
        INC X
        DEC B
        JNZ sh_l
        CMP A, #SYM_SLOTS
        JC sh_ok
        SUB A, #SYM_SLOTS
sh_ok:  ST A, [A_HASH]
        POP X
        RET

; find IDBUF. A = 0 found, 1 free slot (A_SLOT = where it would go), 2 table full
sym_find:
        PUSH X
        CALL sym_hash
        LD A, #SYM_SLOTS
        ST A, [A_PROBES]
sf_l:   LD X, #slot_tab
        LD A, [A_HASH]          ; X += hash * 2
        ADD X, A
        ADD X, A
        LD A, [X+]
        ST A, [A_SLOT]
        LD A, [X]
        ST A, [A_SLOT+1]
        MOV XH, A
        LD A, [A_SLOT]
        MOV XL, A
        LD A, [X]
        CMP A, #0
        JZ sf_free
        CALL cmp_name
        JZ sf_found
        LD A, [A_HASH]
        INC A
        CMP A, #SYM_SLOTS
        JNZ sf_next
        LD A, #0
sf_next:
        ST A, [A_HASH]
        LD A, [A_PROBES]
        DEC A
        ST A, [A_PROBES]
        JNZ sf_l
        LD A, #2
        POP X
        RET
sf_free:
        LD A, #1
        POP X
        RET
sf_found:
        LD A, #0
        POP X
        RET

; define IDBUF = A_VAL. Pass 1: duplicates are errors. Pass 2: value refreshed.
sym_define:
        CALL sym_find
        CMP A, #2
        JZ sd_full
        PUSH X
        CMP A, #0
        JNZ sd_new
        LD A, [A_PASS]
        CMP A, #1
        JZ sd_dup
        JMP sd_val
sd_new: LD A, [A_SLOT]          ; copy the name into the free slot
        MOV XL, A
        LD A, [A_SLOT+1]
        MOV XH, A
        MOV A, SP
        ST A, [SAVE_SP]
        LD SP, #IDBUF_STK
        LD A, #NAME_MAX
        ST A, [T0]
sd_c:   POP B
        ST B, [X+]
        LD A, [T0]
        DEC A
        ST A, [T0]
        JNZ sd_c
        LD A, [SAVE_SP]
        MOV SP, A
sd_val: LD A, [A_SLOT]          ; value after the name, low byte first
        MOV XL, A
        LD A, [A_SLOT+1]
        MOV XH, A
        LD A, #NAME_MAX
        ADD X, A
        LD A, [A_VAL]
        ST A, [X+]
        LD A, [A_VAL+1]
        ST A, [X]
        POP X
        CLC
        RET
sd_dup: POP X
        LD A, #E_DUPLICATE
        JMP fail
sd_full:
        LD A, #E_SYMFULL
        JMP fail

; IDBUF -> A_TERM. C = 1 if undefined. Looks in the table, then predefined names.
sym_value:
        CALL sym_find
        CMP A, #0
        JNZ sv2_pre
        PUSH X
        LD A, [A_SLOT]
        MOV XL, A
        LD A, [A_SLOT+1]
        MOV XH, A
        LD A, #NAME_MAX
        ADD X, A
        JMP sv2_load
sv2_pre:
        PUSH X
        LD X, #predef_tab
sv2_l:  LD A, [X]
        CMP A, #0
        JZ sv2_none
        PUSH X
        CALL cmp_name
        POP X
        JZ sv2_hit
        LD A, #NAME_MAX + 2
        ADD X, A
        JMP sv2_l
sv2_hit:
        LD A, #NAME_MAX
        ADD X, A
sv2_load:
        LD A, [X+]
        ST A, [A_TERM]
        LD A, [X]
        ST A, [A_TERM+1]
        POP X
        CLC
        RET
sv2_none:
        POP X
        SEC
        RET
