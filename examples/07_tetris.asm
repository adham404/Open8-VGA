; TETRIS for Open8-VGA - by Adham Elshafei
; Left/Right: move   Up or X: rotate   Z: rotate back
; Down: soft drop    Space: hard drop  P: pause   ESC: quit

FX = 30                 ; screen column of the field's left edge
FY = 5                  ; screen row of the field's top row
NX = 58                 ; next-piece preview column
TILE0 = 198             ; our own tiles: 198/199 empty, 200..213 pieces

start:  CALL make_tiles
new_game:
        CALL CLS
        CALL draw_static
        CALL clear_board
        LD A, #0
        ST A, [score]
        ST A, [score+1]
        ST A, [lines]
        ST A, [lines+1]
        ST A, [level]
        LD A, #10
        ST A, [tolevel]
        CALL rand_piece
        ST A, [next]
        CALL spawn
        CALL draw_all
loop:   CALL WAITVBL
        CALL handle_keys
        JC game_over
        LD A, [timer]
        DEC A
        ST A, [timer]
        JNZ redraw
        CALL set_timer
        CALL step_down
        JC game_over
redraw: LD A, [dirty]
        CMP A, #0
        JZ loop
        CALL draw_all
        JMP loop

game_over:
        CALL draw_all
        LD A, #FX + 5
        LD B, #FY + 8
        CALL GOTOXY
        LD X, #t_over
        CALL PRINT
        LD A, #FX
        LD B, #FY + 10
        CALL GOTOXY
        LD X, #t_again
        CALL PRINT
go_key: CALL GETKEY
        CMP A, #K_ESC
        JZ quit
        CMP A, #K_ENTER
        JNZ go_key
        JMP new_game
quit:   CALL EXIT

; ------------------------------------------------------------ game logic
; candidate position tx, ty, trot for the current piece: C = 1 if it collides
fits:   LD A, [piece]
        SHL A
        SHL A
        SHL A
        SHL A
        SHL A
        ST A, [t0]
        LD A, [trot]
        SHL A
        SHL A
        SHL A
        ADD A, [t0]
        LD X, #shapes
        ADD X, A
        LD B, #4
fit_l:  LD A, [X+]
        ADD A, [tx]
        ST A, [cc]
        LD A, [X+]
        ADD A, [ty]
        PUSH X
        CALL cell_addr
        LD A, [X]
        POP X
        CMP A, #0
        JNZ fit_no
        DEC B
        JNZ fit_l
        CLC
        RET
fit_no: SEC
        RET

; A = row, [cc] = column -> X = address in board (16 bytes per row)
cell_addr:
        ST A, [cr]
        SHR A
        SHR A
        SHR A
        SHR A
        ADD A, #>board
        MOV XH, A
        LD A, [cr]
        SHL A
        SHL A
        SHL A
        SHL A
        ADD A, [cc]
        MOV XL, A
        RET

; tx, ty, trot <- current position
cur_to_t:
        LD A, [px]
        ST A, [tx]
        LD A, [py]
        ST A, [ty]
        LD A, [rot]
        ST A, [trot]
        RET

; move down one row; if blocked, lock the piece and take the next one.
; C = 1 if the new piece does not fit (game over).
step_down:
        CALL cur_to_t
        LD A, [ty]
        INC A
        ST A, [ty]
        CALL fits
        JC sd_lock
        LD A, [ty]
        ST A, [py]
        LD A, #1
        ST A, [dirty]
        CLC
        RET
sd_lock:
        CALL lock_piece
        CALL clear_lines
        JMP spawn

; write the current piece into the board
lock_piece:
        CALL cur_to_t
        LD A, [piece]
        INC A
        ST A, [t1]
        CALL shape_ptr
        LD B, #4
lk_l:   LD A, [X+]
        ADD A, [px]
        ST A, [cc]
        LD A, [X+]
        ADD A, [py]
        PUSH X
        CALL cell_addr
        LD A, [t1]
        ST A, [X]
        POP X
        DEC B
        JNZ lk_l
        RET

; X -> 8 bytes (dx, dy) x 4 for piece / rot
shape_ptr:
        LD A, [piece]
        SHL A
        SHL A
        SHL A
        SHL A
        SHL A
        ST A, [t0]
        LD A, [rot]
        SHL A
        SHL A
        SHL A
        ADD A, [t0]
        LD X, #shapes
        ADD X, A
        RET

; remove full rows, update score / lines / level
clear_lines:
        LD A, #0
        ST A, [cleared]
        LD A, #19
        ST A, [lr]
cl_row: LD A, #2
        ST A, [cc]
        LD A, [lr]
        CALL cell_addr
        LD B, #10
cl_chk: LD A, [X+]
        CMP A, #0
        JZ cl_next
        DEC B
        JNZ cl_chk
        CALL remove_row         ; full: drop everything above, test this row again
        LD A, [cleared]
        INC A
        ST A, [cleared]
        JMP cl_row
cl_next:
        LD A, [lr]
        DEC A
        ST A, [lr]
        JNC cl_row
        LD A, [cleared]
        CMP A, #0
        JZ cl_end
        SHL A                   ; score += points[cleared]
        LD X, #points
        ADD X, A
        LD A, [score]
        ADD A, [X]
        ST A, [score]
        INC X
        LD A, [score+1]
        ADC A, [X]
        ST A, [score+1]
        LD A, [lines]
        ADD A, [cleared]
        ST A, [lines]
        LD A, [lines+1]
        ADC A, #0
        ST A, [lines+1]
        LD A, [tolevel]         ; every 10 lines: next level
        SUB A, [cleared]
        ST A, [tolevel]
        JZ cl_up
        JNC cl_end
cl_up:  ADD A, #10
        ST A, [tolevel]
        LD A, [level]
        CMP A, #19
        JZ cl_end
        INC A
        ST A, [level]
cl_end: RET

; copy every row above [lr] one row down, clear row 0
remove_row:
        LD A, [lr]
        ST A, [rr]
rm_row: LD A, [rr]
        CMP A, #0
        JZ rm_top
        LD A, #2
        ST A, [cc]
rm_c:   LD A, [rr]
        DEC A
        CALL cell_addr
        LD B, [X]
        LD A, [rr]
        CALL cell_addr
        ST B, [X]
        LD A, [cc]
        INC A
        ST A, [cc]
        CMP A, #12
        JNZ rm_c
        LD A, [rr]
        DEC A
        ST A, [rr]
        JMP rm_row
rm_top: LD A, #2
        ST A, [cc]
        LD A, #0
        CALL cell_addr
        LD A, #0
        LD B, #10
rm_z:   ST A, [X+]
        DEC B
        JNZ rm_z
        LD A, #1
        ST A, [dirty]
        RET

; next piece becomes current. C = 1 if it does not fit.
spawn:  LD A, [next]
        ST A, [piece]
        CALL rand_piece
        ST A, [next]
        LD A, #5
        ST A, [px]
        LD A, #0
        ST A, [py]
        ST A, [rot]
        LD A, #1
        ST A, [dirty]
        CALL set_timer
        CALL cur_to_t
        JMP fits

rand_piece:
        CALL RANDOM
        AND A, #7
        CMP A, #7
        JZ rand_piece
        RET

set_timer:
        LD X, #speeds
        LD A, [level]
        ADD X, A
        LD A, [X]
        ST A, [timer]
        RET

; empty board inside walls (columns 2-11, rows 0-19)
clear_board:
        LD X, #board
cb_l:   LD A, #8                ; wall
        MOV B, A
        MOV A, XL
        AND A, #15
        CMP A, #2
        JC cb_put
        CMP A, #12
        JNC cb_put
        LD B, #0
cb_put: MOV A, XH               ; rows 20+ are floor
        CMP A, #>board
        JZ cb_store
        MOV A, XL
        CMP A, #$40
        JC cb_store
        LD B, #8
cb_store:
        ST B, [X+]
        MOV A, XH
        CMP A, #>board + 1
        JNZ cb_l
        MOV A, XL
        CMP A, #$60
        JNZ cb_l
        RET

; ------------------------------------------------------------ keyboard
; C = 1 if a hard drop ended the game
handle_keys:
        CALL KEYHIT
        CMP A, #0
        JZ hk_done
        CMP A, #K_LEFT
        JZ hk_left
        CMP A, #K_RIGHT
        JZ hk_right
        CMP A, #K_UP
        JZ hk_rot
        CMP A, #'x'
        JZ hk_rot
        CMP A, #'z'
        JZ hk_rotb
        CMP A, #K_DOWN
        JZ hk_down
        CMP A, #' '
        JZ hk_drop
        CMP A, #'p'
        JZ hk_pause
        CMP A, #K_ESC
        JZ quit
        JMP handle_keys
hk_done:
        CLC
        RET
hk_left:
        CALL cur_to_t
        LD A, [tx]
        DEC A
        JMP hk_tryx
hk_right:
        CALL cur_to_t
        LD A, [tx]
        INC A
hk_tryx:
        ST A, [tx]
        CALL fits
        JC handle_keys
        LD A, [tx]
        ST A, [px]
        LD A, #1
        ST A, [dirty]
        JMP handle_keys
hk_rot: LD A, #1
        JMP hk_turn
hk_rotb:
        LD A, #3
hk_turn:
        ST A, [t0]
        CALL cur_to_t
        LD A, [t0]
        ADD A, [rot]
        AND A, #3
        ST A, [trot]
        LD X, #kicks            ; try x offsets 0, -1, +1, -2, +2
hk_k:   LD A, [X+]
        CMP A, #$80
        JZ handle_keys          ; no position fits: no rotation
        ADD A, [px]
        ST A, [tx]
        PUSH X
        CALL fits
        POP X
        JC hk_k
        LD A, [tx]
        ST A, [px]
        LD A, [trot]
        ST A, [rot]
        LD A, #1
        ST A, [dirty]
        JMP handle_keys
hk_down:
        CALL step_down
        JC hk_end
        JMP handle_keys
hk_drop:
        CALL cur_to_t           ; fall until blocked, 2 points per row
hd_l:   LD A, [ty]
        INC A
        ST A, [ty]
        CALL fits
        JC hd_land
        LD A, [ty]
        ST A, [py]
        LD A, [score]
        ADD A, #2
        ST A, [score]
        LD A, [score+1]
        ADC A, #0
        ST A, [score+1]
        JMP hd_l
hd_land:
        CALL step_down          ; locks the piece
        JC hk_end
        JMP handle_keys
hk_pause:
        LD A, #FX + 7
        LD B, #FY + 8
        CALL GOTOXY
        LD X, #t_pause
        CALL PRINT
        CALL GETKEY
        LD A, #1
        ST A, [dirty]
        JMP handle_keys
hk_end: RET

; ------------------------------------------------------------ drawing
; A = column, B = row -> X = VRAM address (screen not scrolled)
vpos:   ST A, [vc]
        MOV A, B
        SHR A
        JNC vp_even
        ADD A, #>VRAM
        MOV XH, A
        LD A, [vc]
        ADD A, #128
        MOV XL, A
        RET
vp_even:
        ADD A, #>VRAM
        MOV XH, A
        LD A, [vc]
        MOV XL, A
        RET

draw_all:
        LD A, #0
        ST A, [dirty]
        LD A, #0                ; field
        ST A, [lr]
da_row: LD A, [lr]
        ADD A, #FY
        MOV B, A
        LD A, #FX
        CALL vpos
        LD A, #2
        ST A, [cc]
da_c:   PUSH X
        LD A, [lr]
        CALL cell_addr
        LD B, [X]
        POP X
        MOV A, B
        SHL A
        ADD A, #TILE0
        ST A, [X+]
        INC A
        ST A, [X+]
        LD A, [cc]
        INC A
        ST A, [cc]
        CMP A, #12
        JNZ da_c
        LD A, [lr]
        INC A
        ST A, [lr]
        CMP A, #20
        JNZ da_row
        CALL shape_ptr          ; current piece on top
        LD A, [piece]
        INC A
        SHL A
        ADD A, #TILE0
        ST A, [t1]
        LD B, #4
dp_l:   LD A, [X+]
        ADD A, [px]
        SUB A, #2
        SHL A
        ADD A, #FX
        ST A, [t2]
        LD A, [X+]
        ADD A, [py]
        ADD A, #FY
        PUSH X
        PUSH B
        MOV B, A
        LD A, [t2]
        CALL vpos
        LD A, [t1]
        ST A, [X+]
        INC A
        ST A, [X]
        POP B
        POP X
        DEC B
        JNZ dp_l
        LD B, #7                ; next piece preview: clear, then draw
dn_clr: MOV A, B
        PUSH B
        LD A, #NX
        CALL vpos
        LD A, #' '
        LD B, #8
dn_c2:  ST A, [X+]
        DEC B
        JNZ dn_c2
        POP B
        INC B
        MOV A, B
        CMP A, #11
        JNZ dn_clr
        LD A, [next]
        SHL A
        SHL A
        SHL A
        SHL A
        SHL A
        LD X, #shapes
        ADD X, A
        LD A, [next]
        INC A
        SHL A
        ADD A, #TILE0
        ST A, [t1]
        LD B, #4
dn_l:   LD A, [X+]
        SHL A
        ADD A, #NX
        ST A, [t2]
        LD A, [X+]
        ADD A, #7
        PUSH X
        PUSH B
        MOV B, A
        LD A, [t2]
        CALL vpos
        LD A, [t1]
        ST A, [X+]
        INC A
        ST A, [X]
        POP B
        POP X
        DEC B
        JNZ dn_l
        LD A, #NX               ; numbers
        LD B, #13
        CALL GOTOXY
        LD A, [score]
        MOV XL, A
        LD A, [score+1]
        MOV XH, A
        CALL PRDEC16
        LD X, #t_pad
        CALL PRINT
        LD A, #NX
        LD B, #16
        CALL GOTOXY
        LD A, [lines]
        MOV XL, A
        LD A, [lines+1]
        MOV XH, A
        CALL PRDEC16
        LD X, #t_pad
        CALL PRINT
        LD A, #NX
        LD B, #19
        CALL GOTOXY
        LD A, [level]
        CALL PRDEC
        RET

draw_static:
        LD A, #FX - 2           ; walls and floor
        ST A, [t2]
        LD B, #FY
ds_w:   PUSH B
        LD A, #FX - 2
        CALL vpos
        LD A, #1
        ST A, [X+]
        ST A, [X]
        POP B
        PUSH B
        LD A, #FX + 20
        CALL vpos
        LD A, #1
        ST A, [X+]
        ST A, [X]
        POP B
        INC B
        MOV A, B
        CMP A, #FY + 20
        JNZ ds_w
        LD A, #FX - 2
        CALL vpos
        LD A, #1
        LD B, #24
ds_f:   ST A, [X+]
        DEC B
        JNZ ds_f
        LD X, #labels           ; texts: column, row, string
ds_t:   LD A, [X+]
        CMP A, #0
        JZ ds_end
        LD B, [X+]
        PUSH X
        CALL GOTOXY
        POP X
        CALL PRINT
        JMP ds_t
ds_end: RET

; build tiles 198..213 in font RAM: 8 kinds x (left half, right half)
make_tiles:
        LD X, #FONT + 3168      ; = FONT + 198 * 16
        LD A, #0
        ST A, [t2]              ; kind 0..7
mk_kind:
        PUSH X
        LD X, #fills
        LD A, [t2]
        SHL A
        ADD X, A
        LD A, [X+]
        ST A, [fe]
        LD A, [X]
        ST A, [fo]
        POP X
        LD A, #0                ; left half
        ST A, [t1]
        CALL mk_half
        LD A, #1                ; right half
        ST A, [t1]
        CALL mk_half
        LD A, [t2]
        INC A
        ST A, [t2]
        CMP A, #8
        JNZ mk_kind
        RET

; one 16-row glyph at X; t1 = 0 left / 1 right; fe/fo = fill for even/odd rows
mk_half:
        LD B, #0
mh_l:   LD A, [t2]
        CMP A, #0
        JZ mh_empty
        MOV A, B
        CMP A, #0
        JZ mh_full
        CMP A, #15
        JZ mh_full
        AND A, #1
        JZ mh_ev
        LD A, [fo]
        JMP mh_side
mh_ev:  LD A, [fe]
mh_side:
        PUSH A
        LD A, [t1]
        CMP A, #0
        POP A
        JNZ mh_r
        AND A, #$7F             ; left half: border on the left edge
        OR A, #$80
        JMP mh_put
mh_r:   AND A, #$FE             ; right half: border on the right edge
        OR A, #$01
        JMP mh_put
mh_full:
        LD A, #$FF
        JMP mh_put
mh_empty:                       ; empty cell: a small dot in the middle
        LD A, #0
        MOV A, B
        CMP A, #7
        JZ mh_dot
        CMP A, #8
        JZ mh_dot
        LD A, #0
        JMP mh_put
mh_dot: LD A, [t1]
        CMP A, #0
        JNZ mh_dotr
        LD A, #$01
        JMP mh_put
mh_dotr:
        LD A, #$80
mh_put: ST A, [X+]
        INC B
        MOV A, B
        CMP A, #16
        JNZ mh_l
        RET

; ------------------------------------------------------------ data
; 7 pieces x 4 rotations x 4 cells (dx, dy): I O T S Z J L
shapes: .db 0,1, 1,1, 2,1, 3,1,   2,0, 2,1, 2,2, 2,3
        .db 0,2, 1,2, 2,2, 3,2,   1,0, 1,1, 1,2, 1,3
        .db 1,0, 2,0, 1,1, 2,1,   1,0, 2,0, 1,1, 2,1
        .db 1,0, 2,0, 1,1, 2,1,   1,0, 2,0, 1,1, 2,1
        .db 1,0, 0,1, 1,1, 2,1,   1,0, 1,1, 2,1, 1,2
        .db 0,1, 1,1, 2,1, 1,2,   1,0, 0,1, 1,1, 1,2
        .db 1,0, 2,0, 0,1, 1,1,   1,0, 1,1, 2,1, 2,2
        .db 1,1, 2,1, 0,2, 1,2,   0,0, 0,1, 1,1, 1,2
        .db 0,0, 1,0, 1,1, 2,1,   2,0, 1,1, 2,1, 1,2
        .db 0,1, 1,1, 1,2, 2,2,   1,0, 0,1, 1,1, 0,2
        .db 0,0, 0,1, 1,1, 2,1,   1,0, 2,0, 1,1, 1,2
        .db 0,1, 1,1, 2,1, 2,2,   1,0, 1,1, 0,2, 1,2
        .db 2,0, 0,1, 1,1, 2,1,   1,0, 1,1, 1,2, 2,2
        .db 0,1, 1,1, 2,1, 0,2,   0,0, 1,0, 1,1, 1,2
kicks:  .db 0, $FF, 1, $FE, 2, $80
fills:  .db 0,0, $FF,$FF, $AA,$55, $FF,$00, $88,$22, $CC,$CC, $00,$00, $EE,$BB
points: .dw 0, 40, 100, 300, 1200
speeds: .db 48, 43, 38, 33, 28, 23, 18, 13, 8, 6, 5, 5, 5, 4, 4, 4, 3, 3, 3, 2
labels: .db FX + 3, 2
        .db "O P E N 8   T E T R I S", 0
        .db NX, 5
        .db "NEXT", 0
        .db NX, 12
        .db "SCORE", 0
        .db NX, 15
        .db "LINES", 0
        .db NX, 18
        .db "LEVEL", 0
        .db 3, 6
        .db "<- ->   move", 0
        .db 3, 7
        .db "UP / X  rotate", 0
        .db 3, 8
        .db "Z       rotate back", 0
        .db 3, 9
        .db "DOWN    soft drop", 0
        .db 3, 10
        .db "SPACE   hard drop", 0
        .db 3, 11
        .db "P       pause", 0
        .db 3, 12
        .db "ESC     quit", 0
        .db 3, 27
        .db "by Adham Elshafei", 0
        .db 0
t_over: .db " GAME  OVER ", 0
t_again: .db "ENTER=play  ESC=quit", 0
t_pad:  .db "   ", 0
t_pause: .db " PAUSED ", 0

px:     .db 0
py:     .db 0
rot:    .db 0
piece:  .db 0
next:   .db 0
tx:     .db 0
ty:     .db 0
trot:   .db 0
cc:     .db 0
cr:     .db 0
lr:     .db 0
rr:     .db 0
t0:     .db 0
t1:     .db 0
t2:     .db 0
vc:     .db 0
fe:     .db 0
fo:     .db 0
timer:  .db 0
dirty:  .db 0
level:  .db 0
tolevel: .db 0
cleared: .db 0
score:  .dw 0
lines:  .dw 0

        .org $9000              ; the board must start on a 256-byte boundary
board:  .ds 352                 ; 22 rows x 16 columns
