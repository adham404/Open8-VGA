; ARITHMETIC - add, subtract, multiply and divide 8-bit numbers.

start:  CALL CLS
        LD X, #t_add        ; 25 + 17
        CALL PRINT
        LD A, #25
        ADD A, #17
        CALL PRDEC
        CALL NEWLINE

        LD X, #t_sub        ; 100 - 58
        CALL PRINT
        LD A, #100
        SUB A, #58
        CALL PRDEC
        CALL NEWLINE

        LD X, #t_mul        ; 6 * 7 by repeated addition
        CALL PRINT
        LD A, #0
        LD B, #7
mul:    ADD A, #6
        DEC B
        JNZ mul
        CALL PRDEC
        CALL NEWLINE

        LD X, #t_div        ; 200 / 7 by repeated subtraction
        CALL PRINT
        LD A, #200
        LD B, #0
div:    CMP A, #7
        JC div_done         ; A < 7: finished
        SUB A, #7
        INC B
        JMP div
div_done:
        PUSH A              ; remainder
        MOV A, B
        CALL PRDEC
        LD X, #t_rem
        CALL PRINT
        POP A
        CALL PRDEC
        CALL NEWLINE
        RET

t_add:  .db "25 + 17 = ", 0
t_sub:  .db "100 - 58 = ", 0
t_mul:  .db "6 * 7 = ", 0
t_div:  .db "200 / 7 = ", 0
t_rem:  .db " remainder ", 0
