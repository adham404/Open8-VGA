; LOOP - count from 1 to 10 with a counter in register B.

start:  CALL CLS
        LD B, #1            ; the counter
loop:   LD X, #t_count
        CALL PRINT          ; PRINT keeps B safe
        MOV A, B
        CALL PRDEC
        CALL NEWLINE
        INC B
        MOV A, B
        CMP A, #11          ; stop after 10
        JNZ loop
        LD X, #t_done
        CALL PRINT
        RET

t_count: .db "Count: ", 0
t_done:  .db "Done!", 10, 0
