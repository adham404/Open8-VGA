; BOUNCE - a ball bouncing around the screen, 60 frames per second.
; Shows direct video memory writes and WAITVBL. Press ESC to stop.

BALL = 25                   ; tile number of the coin/ball tile

start:  CALL CLS
        LD A, #40
        ST A, [bx]
        LD A, #15
        ST A, [by]
frame:  CALL WAITVBL
        LD A, #' '          ; erase the ball
        CALL plot
        LD A, [bx]          ; x += dx, bounce at the edges
        ADD A, [dx]
        ST A, [bx]
        CMP A, #0
        JZ flipx
        CMP A, #79
        JNZ movey
flipx:  LD A, #0
        SUB A, [dx]
        ST A, [dx]
movey:  LD A, [by]
        ADD A, [dy]
        ST A, [by]
        CMP A, #0
        JZ flipy
        CMP A, #29
        JNZ draw
flipy:  LD A, #0
        SUB A, [dy]
        ST A, [dy]
draw:   LD A, #BALL
        CALL plot
        CALL KEYHIT
        CMP A, #K_ESC
        JNZ frame
        RET

; write tile A at (bx, by): address = VRAM + by*128 + bx
plot:   PUSH A
        LD A, [by]
        SHR A               ; by/2 -> high byte offset, C = odd row
        ADD A, #>VRAM
        MOV XH, A
        LD A, [by]
        AND A, #1
        JZ even
        LD A, #128
even:   ADD A, [bx]
        MOV XL, A
        POP A
        ST A, [X]
        RET

bx:     .db 0
by:     .db 0
dx:     .db 1
dy:     .db 1
