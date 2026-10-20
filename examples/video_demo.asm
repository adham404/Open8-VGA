; Open8-VGA video demo — draws text, a Tetris well and a platformer scene
; entirely with CPU writes to VRAM (tile map 128 x 32, 80 x 30 visible).
; Author: Adham Elshafei

ROW = 128                       ; bytes per tile-map row

start:  LD SP, #0
        LD X, #fills
        CALL fill_list
        LD X, #texts
        CALL print_list
        HLT

; ---------------------------------------------------------------- fill_list
; X -> records: .dw dest, .db count, tile, step(1=right, 128=down); .dw 0 ends.
fill_list:
        LD A, [X+]
        ST A, [dst]
        LD A, [X+]
        ST A, [dst+1]
        OR A, [dst]             ; dest == 0 ends the list
        JZ fl_done
        LD A, [X+]
        ST A, [count]
        LD A, [X+]
        ST A, [tile]
        LD A, [X+]
        ST A, [step]
        PUSH X
        LD A, [dst]
        MOV XL, A
        LD A, [dst+1]
        MOV XH, A
        LD B, [count]
fl_loop: LD A, [tile]
        ST A, [X]
        LD A, [step]
        ADD X, A
        DEC B
        JNZ fl_loop
        POP X
        JMP fill_list
fl_done: RET

; --------------------------------------------------------------- print_list
; X -> records: .dw dest, then text bytes, 0; .dw 0 ends.
print_list:
        LD A, [X+]
        ST A, [dst]
        LD A, [X+]
        ST A, [dst+1]
        OR A, [dst]
        JZ pl_done
pl_char: LD B, [X+]
        MOV A, B
        CMP A, #0
        JZ print_list
        PUSH X
        LD A, [dst]
        MOV XL, A
        LD A, [dst+1]
        MOV XH, A
        ST B, [X+]
        MOV A, XL
        ST A, [dst]
        MOV A, XH
        ST A, [dst+1]
        POP X
        JMP pl_char
pl_done: RET

; ------------------------------------------------------------------- data
dst:    .dw 0
count:  .db 0
tile:   .db 0
step:   .db 0

fills:
        ; screen border (box-drawing tiles 8..13)
        .dw VRAM + 0*ROW + 1
        .db 78, 8, 1
        .dw VRAM + 29*ROW + 1
        .db 78, 8, 1
        .dw VRAM + 1*ROW + 0
        .db 28, 9, ROW
        .dw VRAM + 1*ROW + 79
        .db 28, 9, ROW
        .dw VRAM + 0*ROW + 0
        .db 1, 10, 1
        .dw VRAM + 0*ROW + 79
        .db 1, 11, 1
        .dw VRAM + 29*ROW + 0
        .db 1, 12, 1
        .dw VRAM + 29*ROW + 79
        .db 1, 13, 1
        ; Tetris well: walls and floor of solid blocks
        .dw VRAM + 6*ROW + 4
        .db 16, 1, ROW
        .dw VRAM + 6*ROW + 15
        .db 16, 1, ROW
        .dw VRAM + 21*ROW + 4
        .db 12, 1, 1
        ; settled pieces
        .dw VRAM + 20*ROW + 5
        .db 10, 19, 1
        .dw VRAM + 19*ROW + 5
        .db 4, 19, 1
        .dw VRAM + 19*ROW + 10
        .db 5, 19, 1
        .dw VRAM + 18*ROW + 12
        .db 2, 19, 1
        ; falling T piece
        .dw VRAM + 9*ROW + 8
        .db 3, 19, 1
        .dw VRAM + 10*ROW + 9
        .db 1, 19, 1
        ; platformer: ground, bricks, ? blocks, pipe, coins, clouds, hero, enemy
        .dw VRAM + 27*ROW + 20
        .db 59, 22, 1
        .dw VRAM + 28*ROW + 20
        .db 59, 22, 1
        .dw VRAM + 21*ROW + 34
        .db 5, 20, 1
        .dw VRAM + 21*ROW + 36
        .db 1, 21, 1
        .dw VRAM + 17*ROW + 36
        .db 1, 21, 1
        .dw VRAM + 23*ROW + 60
        .db 4, 23, ROW
        .dw VRAM + 23*ROW + 61
        .db 4, 24, ROW
        .dw VRAM + 19*ROW + 34
        .db 5, 25, 1
        .dw VRAM + 8*ROW + 30
        .db 1, 29, 1
        .dw VRAM + 9*ROW + 52
        .db 1, 29, 1
        .dw VRAM + 7*ROW + 66
        .db 1, 29, 1
        .dw VRAM + 26*ROW + 26
        .db 1, 27, 1
        .dw VRAM + 26*ROW + 46
        .db 1, 28, 1
        .dw VRAM + 26*ROW + 50
        .db 1, 28, 1
        .dw VRAM + 3*ROW + 70
        .db 3, 26, 1
        .dw 0

texts:
        .dw VRAM + 2*ROW + 3
        .db "OPEN8-VGA  Phase 3 video test  -  designed by Adham Elshafei", 0
        .dw VRAM + 3*ROW + 3
        .db "80x30 text on a 128x32 tile map, 8x16 cells, 640x480 @ 59.94 Hz", 0
        .dw VRAM + 5*ROW + 4
        .db "TETRIS", 0
        .dw VRAM + 5*ROW + 22
        .db "PLATFORMER TILES", 0
        .dw VRAM + 23*ROW + 3
        .db "LINES 2", 0
        .dw VRAM + 24*ROW + 3
        .db "SCORE 0420", 0
        .dw VRAM + 12*ROW + 22
        .db "LD A, [KBD_DATA]   ; read a key", 0
        .dw VRAM + 13*ROW + 22
        .db "ST A, [X+]         ; draw it", 0
        .dw VRAM + 14*ROW + 22
        .db "abcdefghijklmnopqrstuvwxyz 0123456789 !?#$%&*()[]{}<>", 0
        .dw 0
