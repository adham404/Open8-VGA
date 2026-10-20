; Open8-VGA firmware — PS/2 keyboard driver (runtime: GETKEY KEYHIT KEYDOWN)
; Author: Adham Elshafei
;
; The receiver hardware holds one byte and keeps the keyboard waiting (CLK held
; low) until it is read, so nothing is lost while the CPU is busy; the keyboard's
; own buffer queues further bytes. This driver decodes scan code set 2:
; E0 = extended prefix, F0 = release prefix. It tracks Shift, Ctrl, Caps Lock and
; a 128-bit "key is held" map used by KEYDOWN (for games).

kb_init:
        LD A, #0
        ST A, [KB_FLAGS]
        LD X, #KEYDOWN_MAP
        LD B, #16
ki_l:   ST A, [X+]
        DEC B
        JNZ ki_l
ki_drain:                       ; discard anything pressed during reset
        LD A, [KBD_STATUS]
        AND A, #1
        JZ ki_end
        LD A, [KBD_DATA]
        JMP ki_drain
ki_end: RET

; ---------------------------------------------------------------- KEYHIT
; A = next key code, or 0 if no key is waiting. Never waits.
r_keyhit:
        LD A, [KBD_STATUS]
        AND A, #1
        JZ kh_none
kh_byte:
        CALL kb_byte
        CMP A, #0
        JNZ kh_ret
        CALL kb_wait_rest       ; inside an E0/F0 sequence: wait for its last byte
        JC kh_byte
        JMP r_keyhit
kh_none:
        LD A, #0
kh_ret: RET

; If an E0/F0 prefix was just received, wait up to ~2 ms for the next byte.
; C = 1 if a byte is now waiting. Preserves B and X.
kb_wait_rest:
        LD A, [KB_FLAGS]
        AND A, #3
        JZ kw_no
        PUSH B
        LD B, #0
kw_l:   LD A, [KBD_STATUS]
        AND A, #1
        JNZ kw_yes
        DEC B
        JNZ kw_l
        POP B
kw_no:  CLC
        RET
kw_yes: POP B
        SEC
        RET

; ---------------------------------------------------------------- GETKEY
; Waits for a key; shows an inverse cursor at the console position meanwhile.
; A = key code: ASCII, or K_ENTER(10) K_BS(8) K_TAB(9) K_ESC(27), K_UP.. K_F12 (>= $80)
r_getkey:
        PUSH B
        PUSH X
        LD A, [CON_X]
        LD B, [CON_Y]
        CALL vaddr
        LD A, [X]
        XOR A, #$80
        ST A, [X]
gk_l:   CALL rng_step           ; key timing seeds the random generator
        CALL r_keyhit
        CMP A, #0
        JZ gk_l
        MOV B, A
        LD A, [X]
        XOR A, #$80
        ST A, [X]
        MOV A, B
        POP X
        POP B
        RET

; ---------------------------------------------------------------- KEYDOWN
; A = set-2 scan code (SC_LEFT, SC_SPACE, ...). Returns A = 1 if the key is held,
; else 0 (Z flag set accordingly). Pending keyboard bytes are processed first;
; key codes produced by them are discarded.
r_keydown:
        PUSH B
        PUSH X
        ST A, [T3]
kd_drain:
        LD A, [KBD_STATUS]
        AND A, #1
        JZ kd_test
kd_byte:
        CALL kb_byte
        CALL kb_wait_rest
        JC kd_byte
        JMP kd_drain
kd_test:
        LD A, [T3]
        CALL kd_locate          ; X -> map byte, B = bit mask
        LD A, [X]
        AND A, B
        JZ kd_no
        LD A, #1
kd_no:  POP X
        POP B
        CMP A, #0
        RET

; A = scan code -> X = address in KEYDOWN_MAP, B = bit mask. Changes A.
kd_locate:
        AND A, #$7F
        PUSH A
        LD X, #bitmask
        AND A, #7
        ADD X, A
        LD B, [X]
        POP A
        SHR A
        SHR A
        SHR A
        LD X, #KEYDOWN_MAP
        ADD X, A
        RET

bitmask: .db 1, 2, 4, 8, 16, 32, 64, 128

; ---------------------------------------------------------------- kb_byte
; Read one byte from the receiver and decode it. A = key code or 0.
; Preserves B and X.
kb_byte:
        PUSH B
        PUSH X
        LD A, [KBD_STATUS]
        ST A, [KB_STAT]
        LD A, [KBD_DATA]
        ST A, [KB_DATA]
        ; frame check: start bit 0, stop bit 1, odd parity
        LD A, [KB_STAT]
        AND A, #$0C
        CMP A, #$08
        JNZ kb_bad
        LD A, [KB_STAT]
        SHR A
        AND A, #1
        ST A, [KB_PAR]
        LD A, [KB_DATA]
        LD B, #8
kp_l:   SHR A
        JNC kp_n
        PUSH A
        LD A, [KB_PAR]
        XOR A, #1
        ST A, [KB_PAR]
        POP A
kp_n:   DEC B
        JNZ kp_l
        LD A, [KB_PAR]
        CMP A, #1
        JNZ kb_bad
        ; prefixes
        LD A, [KB_DATA]
        CMP A, #$E0
        JZ kb_e0
        CMP A, #$F0
        JZ kb_f0
        CMP A, #$83             ; F7 is the only set-2 code above $7F
        JNZ kb_not_f7
        LD A, #$02
        ST A, [KB_DATA]
kb_not_f7:
        CMP A, #$80
        JNC kb_bad              ; $00 overrun, $AA self-test, $FA ack, ...
        CMP A, #0
        JZ kb_bad
        ; update the held-keys map
        CALL kd_locate
        LD A, [KB_FLAGS]
        AND A, #2
        JNZ kb_rel
        MOV A, B
        OR A, [X]
        ST A, [X]
        JMP kb_mods
kb_rel: MOV A, B
        NOT A
        AND A, [X]
        ST A, [X]
kb_mods:
        LD A, [KB_DATA]
        CMP A, #$14             ; Ctrl (left, or right with E0)
        JZ kb_ctrl
        LD A, [KB_FLAGS]
        AND A, #1
        JNZ kb_ext
        LD A, [KB_DATA]
        CMP A, #$12
        JZ kb_shift
        CMP A, #$59
        JZ kb_shift
        LD A, [KB_FLAGS]
        AND A, #2
        JNZ kb_zero             ; other releases produce nothing
        LD A, [KB_DATA]
        CMP A, #$58
        JZ kb_caps
        ; translate through the key map
        LD X, #keymap_plain
        LD A, [KB_FLAGS]
        AND A, #4
        JZ kb_plain
        LD X, #keymap_shift
kb_plain:
        LD A, [KB_DATA]
        ADD X, A
        LD A, [X]
        ST A, [T2]
        LD A, [KB_FLAGS]        ; Caps Lock flips letter case
        AND A, #16
        JZ kb_ctl
        LD A, [T2]
        CALL is_alpha
        JNC kb_ctl
        LD A, [T2]
        XOR A, #$20
        ST A, [T2]
kb_ctl: LD A, [KB_FLAGS]        ; Ctrl + letter -> control code 1-26
        AND A, #8
        JZ kb_out
        LD A, [T2]
        CALL is_alpha
        JNC kb_out
        LD A, [T2]
        AND A, #$1F
        ST A, [T2]
kb_out: CALL kb_clear_prefix
        LD A, [T2]
        JMP kb_ret

kb_e0:  LD A, [KB_FLAGS]
        OR A, #1
        ST A, [KB_FLAGS]
        LD A, #0
        JMP kb_ret
kb_f0:  LD A, [KB_FLAGS]
        OR A, #2
        ST A, [KB_FLAGS]
        LD A, #0
        JMP kb_ret
kb_shift:
        LD A, [KB_FLAGS]
        AND A, #$FB
        ST A, [KB_FLAGS]
        AND A, #2
        JNZ kb_zero
        LD A, [KB_FLAGS]
        OR A, #4
        ST A, [KB_FLAGS]
        JMP kb_zero
kb_ctrl:
        LD A, [KB_FLAGS]
        AND A, #$F7
        ST A, [KB_FLAGS]
        AND A, #2
        JNZ kb_zero
        LD A, [KB_FLAGS]
        OR A, #8
        ST A, [KB_FLAGS]
        JMP kb_zero
kb_caps:
        LD A, [KB_FLAGS]
        XOR A, #16
        ST A, [KB_FLAGS]
        JMP kb_zero
kb_ext:                         ; extended key: look it up in (code, key) pairs
        LD A, [KB_FLAGS]
        AND A, #2
        JNZ kb_zero
        LD X, #keymap_ext
ke_l:   LD A, [X+]
        CMP A, #0
        JZ kb_zero
        CMP A, [KB_DATA]
        JZ ke_hit
        INC X
        JMP ke_l
ke_hit: LD A, [X]
        ST A, [T2]
        JMP kb_out
kb_bad:
kb_zero:
        CALL kb_clear_prefix
        LD A, #0
kb_ret: POP X
        POP B
        RET

kb_clear_prefix:
        LD A, [KB_FLAGS]
        AND A, #$FC
        ST A, [KB_FLAGS]
        RET

; C = 1 if A is a letter
is_alpha:
        CMP A, #'A'
        JC ia_no
        CMP A, #'Z' + 1
        JC ia_yes
        CMP A, #'a'
        JC ia_no
        CMP A, #'z' + 1
        JC ia_yes
ia_no:  CLC
        RET
ia_yes: SEC
        RET
