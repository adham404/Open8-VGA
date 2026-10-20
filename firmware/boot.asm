; Open8-VGA firmware — reset, trap handling, welcome screen
; Author: Adham Elshafei
;
; $0000 is both the reset vector and the invalid-opcode trap target. The TRAP bit
; in SYS_STATUS tells them apart; a trap left the faulting PC on the stack.
; Source text in SRAM survives RESET: if the buffer looks valid we "warm boot"
; straight back into the editor.

boot:
        MOV A, SP               ; before anything touches the stack
        ST A, [TRAP_SP]
        LD SP, #0
        LD A, [SYS_STATUS]
        ST A, [BOOT_STAT]
        ST A, [SYS_STATUS]      ; any write clears TRAP and WRITE-VIOLATION
        LD A, #0
        ST A, [SCROLL_X]
        ST A, [SCROLL_Y]
        ST A, [ROM_BANK]
        ST A, [CON_SCRY]
        LD A, #4                ; SPI: /CS high (EEPROM deselected), SCK low
        ST A, [OUT_PORT]
        LD A, #0
        ST A, [CON_SCRY]
        ST A, [CON_ATTR]
        LD A, [BOOT_STAT]
        AND A, #2
        JZ bt_notrap
        LD A, [TRAP_SP]         ; PC low at $AF00+SP, high at the next byte (page wraps)
        MOV XL, A
        LD A, #>STACK_PAGE
        MOV XH, A
        LD A, [X]
        ST A, [TRAP_PC]
        MOV A, XL
        INC A
        MOV XL, A
        LD A, [X]
        ST A, [TRAP_PC+1]
        LD A, [TRAP_PC]         ; the pushed PC points after the opcode
        SUB A, #1
        ST A, [TRAP_PC]
        LD A, [TRAP_PC+1]
        SBC A, #0
        ST A, [TRAP_PC+1]
bt_notrap:
        CALL kb_init
        CALL font_init
        CALL clear_msg
        LD A, [MAGIC]
        CMP A, #'O'
        JNZ bt_cold
        LD A, [MAGIC+1]
        CMP A, #'8'
        JNZ bt_cold
        CALL ed_check_ptrs
        JC bt_cold
        CALL ed_recount         ; warm boot: keep the text
        LD A, [BOOT_STAT]
        AND A, #2
        JNZ bt_trapmsg
        LD X, #s_reset
        CALL set_msg
        JMP ed_enter
bt_trapmsg:
        LD X, #s_trap
        CALL set_msg
        LD A, #2
        ST A, [MSG_KIND]
        LD A, [TRAP_PC]
        ST A, [MSG_NUM]
        LD A, [TRAP_PC+1]
        ST A, [MSG_NUM+1]
        LD A, #<s_trap2
        ST A, [MSG_POST]
        LD A, #>s_trap2
        ST A, [MSG_POST+1]
        JMP ed_enter

bt_cold:
        LD A, #$E1
        ST A, [RNG]
        LD A, #$AC
        ST A, [RNG+1]
        CALL ed_new
        LD A, #0                ; start with the first example in the editor
        CALL ex_load
        CALL welcome
        JMP ed_enter

; tests call firmware routines with this as the return address
test_halt:
        HLT

welcome:
        LD A, #0
        ST A, [CON_ATTR]
        CALL r_cls
        LD A, #$80
        ST A, [CON_ATTR]
        LD B, #0
        CALL clear_row
        LD X, #s_title
        CALL r_print
        LD A, #0
        ST A, [CON_ATTR]
        LD A, #0
        LD B, #2
        CALL r_gotoxy
        LD X, #s_welcome
        CALL r_print
        CALL r_getkey
        RET
