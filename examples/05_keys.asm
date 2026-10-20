; KEYS - read the keyboard. Typed characters are echoed;
; special keys show their code in hex. ESC returns to the editor.

start:  CALL CLS
        LD X, #t_help
        CALL PRINT
loop:   CALL GETKEY         ; wait for a key, A = key code
        CMP A, #K_ESC
        JZ done
        CMP A, #K_ENTER
        JZ newline
        CMP A, #128         ; codes >= 128 are arrows, F-keys ...
        JNC special
        CALL PUTC
        JMP loop
newline:
        CALL NEWLINE
        JMP loop
special:
        PUSH A
        LD A, #'<'
        CALL PUTC
        POP A
        CALL PRHEX
        LD A, #'>'
        CALL PUTC
        JMP loop
done:   RET

t_help: .db "Type something. ESC goes back to the editor.", 10, 0
