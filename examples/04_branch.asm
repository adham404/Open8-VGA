; BRANCH - make decisions with CMP and conditional jumps.
; For each number in the list: is it even or odd, small or big?

start:  CALL CLS
        LD X, #numbers
next:   LD A, [X+]          ; next number, X moves on
        CMP A, #0
        JZ finished         ; 0 ends the list
        PUSH X
        PUSH A
        CALL PRDEC
        POP A
        PUSH A
        AND A, #1           ; lowest bit: 0 = even, 1 = odd
        JZ even
        LD X, #t_odd
        JMP show
even:   LD X, #t_even
show:   CALL PRINT
        POP A
        CMP A, #100         ; C is set when A < 100
        JC small
        LD X, #t_big
        JMP show2
small:  LD X, #t_small
show2:  CALL PRINT
        POP X
        JMP next
finished:
        RET

numbers: .db 7, 42, 99, 100, 250, 0
t_even:  .db " is even", 0
t_odd:   .db " is odd", 0
t_small: .db " and smaller than 100", 10, 0
t_big:   .db " and 100 or more", 10, 0
