; OPEN8 RUNNER - a scrolling platformer for Open8-VGA - by Adham Elshafei
; Left/Right: run   Space or Up: jump   ESC: quit
; Stomp the walkers, collect coins, bump ? blocks, reach the flag.
;
; SCROLL_X scrolls the 128-column tile map like a ring; new level columns are
; built off-screen. MAP (a RAM copy) is the collision map.

MAP = $9000             ; RAM copy of the tile map (row*128 + col), not part of the program
LEVEL_END = 254         ; last level column
FLAG_COL = 238
SPEED = 48              ; player speed, 1/256 tile per frame
JUMP = 146              ; -110: jump speed (1/256 row per frame, negative = up)
GRAV = 7
ESPEED = 14
HERO = 27
HERO_L = 214            ; hero facing left (built at start)
WALKER = 28
FLAGTILE = 215
SKY = ' '

start:  CALL make_tiles
        LD A, #3
        ST A, [lives]
        LD A, #0
        ST A, [score]
        ST A, [score+1]
        ST A, [coins]
level:  CALL CLS
        LD A, #0
        ST A, [cam]
        ST A, [SCROLL_X]
        ST A, [state]
        ST A, [pxf]
        ST A, [pyf]
        ST A, [vy]
        ST A, [onground]
        ST A, [face]
        ST A, [run_left]
        LD X, #grounds
        CALL save_runptr
        LD X, #e_on
        LD A, #0
        LD B, #6
lv_e:   ST A, [X+]
        DEC B
        JNZ lv_e
        LD A, #3
        ST A, [px]
        LD A, #20
        ST A, [py]
        LD A, #0
        ST A, [gcol]
lv_g:   CALL gen_column
        LD A, [gcol]
        INC A
        ST A, [gcol]
        CMP A, #82
        JNZ lv_g
        CALL hud
        CALL save_drawn

main:   CALL WAITVBL
        CALL erase_sprites
        CALL player
        CALL enemies
        CALL camera
        CALL draw_sprites
        LD A, #SC_ESC
        CALL KEYDOWN
        JNZ quit
        LD A, [state]
        CMP A, #1
        JZ died
        CMP A, #2
        JZ won
        JMP main
quit:   CALL EXIT

died:   LD X, #t_ouch
        CALL banner
        LD A, #60
        CALL DELAY
        LD A, [lives]
        DEC A
        ST A, [lives]
        JNZ level
        LD X, #t_over
        CALL banner
        CALL wait_enter
        JMP start
won:    LD X, #t_clear
        CALL banner
        CALL wait_enter
        JMP start

wait_enter:
        CALL GETKEY
        CMP A, #K_ESC
        JZ quit
        CMP A, #K_ENTER
        JNZ wait_enter
        RET

; == the player ==
player: LD A, #SC_RIGHT
        CALL KEYDOWN
        JZ pl_left
        LD A, #0
        ST A, [face]
        LD A, [pxf]
        ADD A, #SPEED
        ST A, [nxf]
        LD A, [px]
        ADC A, #0
        ST A, [nx]
        CMP A, #LEVEL_END
        JNC pl_vert
        LD A, [nxf]
        CMP A, #0
        LD A, [nx]
        JZ pl_rc
        INC A
pl_rc:  ST A, [mcol]
        CALL solid_rows
        JNC pl_setx
        LD A, [mcol]
        DEC A
        ST A, [nx]
        LD A, #0
        ST A, [nxf]
        JMP pl_setx
pl_left:
        LD A, #SC_LEFT
        CALL KEYDOWN
        JZ pl_vert
        LD A, #1
        ST A, [face]
        LD A, [pxf]
        SUB A, #SPEED
        ST A, [nxf]
        LD A, [px]
        SBC A, #0
        ST A, [nx]
        JC pl_vert
        CMP A, [cam]
        JC pl_vert
        ST A, [mcol]
        CALL solid_rows
        JNC pl_setx
        LD A, [mcol]
        INC A
        ST A, [nx]
        LD A, #0
        ST A, [nxf]
pl_setx:
        LD A, [nx]
        ST A, [px]
        LD A, [nxf]
        ST A, [pxf]
pl_vert:
        LD A, [onground]
        CMP A, #0
        JZ pl_air
        LD A, [py]
        INC A
        CALL solid_cols
        JNC pl_fall
        LD A, #SC_SPACE
        CALL KEYDOWN
        JNZ pl_jump
        LD A, #SC_UP
        CALL KEYDOWN
        JZ pl_items
pl_jump:
        LD A, #JUMP
        ST A, [vy]
        JMP pl_fall
pl_air: LD A, [vy]
        ADD A, #GRAV
        ST A, [vy]
        CMP A, #120
        JC pl_move
        CMP A, #128
        JNC pl_move
        LD A, #120
        ST A, [vy]
        JMP pl_move
pl_fall:
        LD A, #0
        ST A, [onground]
pl_move:
        LD A, [vy]
        AND A, #$80
        JZ pl_vpos
        LD A, #$FF
pl_vpos:
        ST A, [t0]
        LD A, [pyf]
        ADD A, [vy]
        ST A, [nyf]
        LD A, [py]
        ADC A, [t0]
        ST A, [ny]
        CMP A, #28
        JNC pl_dead
        LD A, [t0]
        CMP A, #0
        JZ pl_down
        LD A, [ny]
        CALL solid_cols
        JNC pl_sety
        CALL bump
        LD A, [ny]
        INC A
        ST A, [ny]
        LD A, #0
        ST A, [nyf]
        ST A, [vy]
        JMP pl_sety
pl_down:
        LD A, [nyf]
        CMP A, #0
        JZ pl_sety
        LD A, [ny]
        INC A
        CALL solid_cols
        JNC pl_sety
        LD A, #0
        ST A, [nyf]
        ST A, [vy]
        LD A, #1
        ST A, [onground]
pl_sety:
        LD A, [ny]
        ST A, [py]
        LD A, [nyf]
        ST A, [pyf]
pl_items:
        LD A, [py]
        CALL take_coins
        LD A, [pyf]
        CMP A, #0
        JZ pl_flag
        LD A, [py]
        INC A
        CALL take_coins
pl_flag:
        LD A, [px]
        CMP A, #FLAG_COL - 1
        JC pl_end
        LD A, #2
        ST A, [state]
pl_end: RET
pl_dead:
        LD A, #1
        ST A, [state]
        RET

; A = row: C = 1 if any column we cover in that row is solid
solid_cols:
        ST A, [t1]
        LD A, [px]
        ST A, [mcol]
        LD A, [t1]
        CALL solid_at
        JC sc_end
        LD A, [pxf]
        CMP A, #0
        JZ sc_no
        LD A, [px]
        INC A
        ST A, [mcol]
        LD A, [t1]
        JMP solid_at
sc_no:  CLC
sc_end: RET

; column [mcol]: C = 1 if a row we cover is solid
solid_rows:
        LD A, [py]
        CALL solid_at
        JC sr_end
        LD A, [pyf]
        CMP A, #0
        JZ sc_no
        LD A, [py]
        INC A
        JMP solid_at
sr_end: RET

; A = row, [mcol] = column: C = 1 if solid. X = map address.
solid_at:
        CALL map_addr
        LD A, [X]
is_solid:
        CMP A, #1
        JZ so_yes
        CMP A, #3
        JZ so_yes
        CMP A, #20
        JC so_no
        CMP A, #25
        JC so_yes
        CMP A, #216
        JZ so_yes
        CMP A, #217
        JZ so_yes
so_no:  CLC
        RET
so_yes: SEC
        RET

; A = row, [mcol] = column -> X = MAP + row*128 + (col & 127)
map_addr:
        ST A, [t2]
        LD A, [mcol]
        AND A, #127
        ST A, [t3]
        LD A, [t2]
        SHR A
        JNC ma_even
        ADD A, #>MAP
        MOV XH, A
        LD A, [t3]
        OR A, #128
        MOV XL, A
        RET
ma_even:
        ADD A, #>MAP
        MOV XH, A
        LD A, [t3]
        MOV XL, A
        RET

; tile A into MAP at X and into VRAM at the same position
put_tile:
        ST A, [X]
        PUSH A
        MOV A, XH
        SUB A, #>MAP - >VRAM
        MOV XH, A
        POP A
        ST A, [X]
        MOV A, XH
        ADD A, #>MAP - >VRAM
        MOV XH, A
        RET

; head hit the map at X: a ? block gives a coin and becomes a used block
bump:   LD A, [X]
        CMP A, #21
        JNZ bp_end
        LD A, #3
        CALL put_tile
        CALL add_coin
bp_end: SEC
        RET

; A = row: collect coins in the columns we cover
take_coins:
        ST A, [t1]
        LD A, [px]
        ST A, [mcol]
        CALL tc_one
        LD A, [pxf]
        CMP A, #0
        JZ tc_end
        LD A, [px]
        INC A
        ST A, [mcol]
tc_one: LD A, [t1]
        CALL map_addr
        LD A, [X]
        CMP A, #25
        JNZ tc_end
        LD A, #SKY
        CALL put_tile
add_coin:
        LD A, [coins]
        INC A
        ST A, [coins]
        LD A, #10
        CALL add_score
        CALL hud
tc_end: RET

add_score:
        ADD A, [score]
        ST A, [score]
        LD A, [score+1]
        ADC A, #0
        ST A, [score+1]
        RET

; == walkers ==
enemies:
        LD A, #0
        ST A, [ei]
en_l:   LD X, #e_on
        LD A, [ei]
        ADD X, A
        LD A, [X]
        CMP A, #0
        JZ en_next
        CALL en_load
        LD A, [ex]
        CMP A, [cam]
        JC en_off
        LD A, [edir]
        CMP A, #0
        JNZ en_left
        LD A, [exf]
        ADD A, #ESPEED
        ST A, [exf]
        LD A, [ex]
        ADC A, #0
        ST A, [ex]
        INC A
        JMP en_look
en_left:
        LD A, [exf]
        SUB A, #ESPEED
        ST A, [exf]
        LD A, [ex]
        SBC A, #0
        ST A, [ex]
en_look:
        ST A, [mcol]
        LD A, [ey]
        CALL solid_at
        JC en_turn
        LD A, [ey]
        INC A
        CALL solid_at
        JC en_hit
en_turn:
        LD A, [edir]
        XOR A, #1
        ST A, [edir]
en_hit: CALL en_store
        CALL en_touch
        JMP en_next
en_off: LD X, #e_on
        LD A, [ei]
        ADD X, A
        LD A, #0
        ST A, [X]
en_next:
        LD A, [ei]
        INC A
        ST A, [ei]
        CMP A, #6
        JNZ en_l
        RET

; enemy ei touching the player? stomp from above, otherwise the player dies
en_touch:
        LD A, [pxf]
        SUB A, [exf]
        ST A, [t0]
        LD A, [px]
        SBC A, [ex]
        CALL near
        JNC et_end
        LD A, [pyf]
        ST A, [t0]
        LD A, [py]
        SUB A, [ey]
        CALL near
        JNC et_end
        LD A, [vy]
        CMP A, #0
        JZ et_die
        AND A, #$80
        JNZ et_die
        LD X, #e_on
        LD A, [ei]
        ADD X, A
        LD A, #0
        ST A, [X]
        LD A, #$B0
        ST A, [vy]
        LD A, #100
        CALL add_score
        JMP hud
et_die: LD A, #1
        ST A, [state]
et_end: RET

; A:[t0] = signed 8.8 distance; C = 1 if |d| < 0.75
near:   CMP A, #0
        JZ nr_pos
        CMP A, #$FF
        JNZ nr_far
        LD A, [t0]
        CMP A, #$40
        JC nr_far
        SEC
        RET
nr_pos: LD A, [t0]
        CMP A, #$C0
        RET
nr_far: CLC
        RET

; copy slot ei to ex/exf/ey/edir and back
en_load:
        LD A, [ei]
        CALL en_ptr
        LD A, [X+]
        ST A, [ex]
        LD A, [X+]
        ST A, [exf]
        LD A, [X+]
        ST A, [ey]
        LD A, [X]
        ST A, [edir]
        RET
en_store:
        LD A, [ei]
        CALL en_ptr
        LD A, [ex]
        ST A, [X+]
        LD A, [exf]
        ST A, [X+]
        LD A, [ey]
        ST A, [X+]
        LD A, [edir]
        ST A, [X]
        RET
en_ptr: SHL A
        SHL A
        LD X, #e_data
        ADD X, A
        RET

; start a walker at column [gcol], row A (first free slot)
spawn:  ST A, [t1]
        LD X, #e_on
        LD B, #0
sp_l:   LD A, [X]
        CMP A, #0
        JZ sp_free
        INC X
        INC B
        MOV A, B
        CMP A, #6
        JNZ sp_l
        RET
sp_free:
        LD A, #1
        ST A, [X]
        MOV A, B
        CALL en_ptr
        LD A, [gcol]
        ST A, [X+]
        LD A, #0
        ST A, [X+]
        LD A, [t1]
        ST A, [X+]
        LD A, #1
        ST A, [X]
        RET

; == camera ==
camera: LD A, [px]
        SUB A, #30
        JC cm_end
        CMP A, [cam]
        JC cm_end
        JZ cm_end
        LD A, [cam]
        CMP A, #LEVEL_END - 80
        JNC cm_end
        INC A
        ST A, [cam]
        ST A, [SCROLL_X]
        ADD A, #81
        CMP A, #LEVEL_END + 1
        JNC cm_hud
        ST A, [gcol]
        CALL gen_column
cm_hud: JMP hud
cm_end: RET

; == level building ==
; build level column [gcol] in MAP and VRAM
gen_column:
        LD A, [gcol]
        ST A, [mcol]
        LD A, #0
        CALL map_addr
        LD B, #30
gc_sky: LD A, #SKY
        CALL put_tile
        LD A, #128
        ADD X, A
        DEC B
        JNZ gc_sky
        LD A, [gcol]
        AND A, #31
        CMP A, #7
        JNZ gc_c2
        LD A, #4
        LD B, #29
        CALL gc_put
gc_c2:  LD A, [gcol]
        AND A, #31
        CMP A, #21
        JNZ gc_gnd
        LD A, #7
        LD B, #29
        CALL gc_put
gc_gnd: LD A, [run_left]
        CMP A, #0
        JNZ gc_run
        CALL load_runptr
        LD A, [X+]
        ST A, [run_left]
        LD A, [X+]
        ST A, [run_top]
        CALL save_runptr
gc_run: LD A, [run_left]
        DEC A
        ST A, [run_left]
        LD A, [run_top]
        CMP A, #0
        JZ gc_obj
gc_g:   LD B, #22
        PUSH A
        CALL gc_put
        POP A
        INC A
        CMP A, #30
        JNZ gc_g
gc_obj: LD X, #objects
gc_o:   LD A, [X]
        CMP A, #255
        JZ gc_end
        LD A, [gcol]
        SUB A, [X]
        JC gc_skip
        ST A, [t1]
        PUSH X
        INC X
        LD A, [X+]
        ST A, [orow]
        LD A, [X+]
        ST A, [otile]
        LD A, [X+]
        ST A, [olen]
        LD A, [X]
        ST A, [okind]
        CALL gc_object
        POP X
gc_skip:
        LD A, #5
        ADD X, A
        JMP gc_o
gc_end: RET

; place one object (offset t1 into it, fields orow otile olen okind)
gc_object:
        LD A, [okind]
        CMP A, #1
        JZ go_pipe
        CMP A, #2
        JZ go_enemy
        CMP A, #3
        JZ go_flag
        LD A, [t1]
        CMP A, [olen]
        JNC go_end
        LD A, [orow]
        LD B, [otile]
        JMP gc_put
go_pipe:
        LD A, [t1]
        CMP A, #2
        JNC go_end
        LD B, #23
        CMP A, #0
        JZ go_p
        LD B, #24
go_p:   LD A, [orow]
        ST A, [t2]
gp_l:   LD A, [t2]
        PUSH B
        CALL gc_put
        POP B
        MOV A, B
        CMP A, #200
        JNC gp_body
        ADD A, #193
        MOV B, A
gp_body:
        LD A, [t2]
        INC A
        ST A, [t2]
        LD A, [olen]
        DEC A
        ST A, [olen]
        JNZ gp_l
go_end: RET
go_enemy:
        LD A, [t1]
        CMP A, #0
        JNZ go_end
        LD A, [orow]
        JMP spawn
go_flag:
        LD A, [t1]
        CMP A, #0
        JNZ go_end
        LD A, [orow]
        LD B, #FLAGTILE
        CALL gc_put
        LD A, [orow]
        ST A, [t2]
gf_l:   LD A, [t2]
        INC A
        ST A, [t2]
        CMP A, #26
        JZ gf_base
        LD B, #'|'
        CALL gc_put
        JMP gf_l
gf_base:
        LD B, #1
gc_put: PUSH B
        PUSH A
        LD A, [gcol]
        ST A, [mcol]
        POP A
        CALL map_addr
        POP A
        JMP put_tile

load_runptr:
        LD A, [runptr]
        MOV XL, A
        LD A, [runptr+1]
        MOV XH, A
        RET
save_runptr:
        MOV A, XL
        ST A, [runptr]
        MOV A, XH
        ST A, [runptr+1]
        RET

; == sprites ==
; screen position of the player / an enemy (rounded) -> X = VRAM address
draw_sprites:
        CALL save_drawn
        LD A, [d_px]
        ST A, [mcol]
        LD A, [d_py]
        CALL map_addr
        CALL to_vram
        LD A, #HERO
        LD B, [face]
        DEC B
        JNZ ds_hero
        LD A, #HERO_L
ds_hero:
        ST A, [X]
        LD A, #0
        ST A, [ei]
ds_e:   LD X, #e_on
        LD A, [ei]
        ADD X, A
        LD A, [X]
        CMP A, #0
        JZ ds_n
        CALL en_load
        LD A, [exf]
        ADD A, #128
        LD A, [ex]
        ADC A, #0
        ST A, [mcol]
        LD A, [ey]
        CALL map_addr
        CALL to_vram
        LD A, #WALKER
        ST A, [X]
ds_n:   LD A, [ei]
        INC A
        ST A, [ei]
        CMP A, #6
        JNZ ds_e
        RET

; remember where the player is drawn (rounded position)
save_drawn:
        LD A, [pxf]
        ADD A, #128
        LD A, [px]
        ADC A, #0
        ST A, [d_px]
        LD A, [pyf]
        ADD A, #128
        LD A, [py]
        ADC A, #0
        ST A, [d_py]
        RET

; restore the map tiles under the sprites
erase_sprites:
        LD A, [d_px]
        ST A, [mcol]
        LD A, [d_py]
        CALL restore
        LD A, #0
        ST A, [ei]
er_l:   LD X, #e_on
        LD A, [ei]
        ADD X, A
        LD A, [X]
        CMP A, #0
        JZ er_n
        CALL en_load
        LD A, [ex]
        ST A, [mcol]
        LD A, [ey]
        CALL restore
        LD A, [ex]
        INC A
        ST A, [mcol]
        LD A, [ey]
        CALL restore
er_n:   LD A, [ei]
        INC A
        ST A, [ei]
        CMP A, #6
        JNZ er_l
        RET

; copy MAP to VRAM at row A, column [mcol]
restore:
        CALL map_addr
        LD A, [X]
        PUSH A
        CALL to_vram
        POP A
        ST A, [X]
        RET

to_vram:
        MOV A, XH
        SUB A, #>MAP - >VRAM
        MOV XH, A
        RET

; == text ==
; status line on row 1, at the scrolled position
hud:    LD X, #hudbuf + 8
        LD A, [score]
        ST A, [n16]
        LD A, [score+1]
        ST A, [n16+1]
        CALL dec5
        LD X, #hudbuf + 21
        LD A, [coins]
        ST A, [n16]
        LD A, #0
        ST A, [n16+1]
        CALL dec5
        LD A, [lives]
        ADD A, #'0'
        ST A, [hudbuf + 34]
        LD X, #hudbuf           ; leading spaces erase what scrolled past
        LD A, #0
        LD B, #1
; X = text, A = screen column, B = row: write it at the scrolled position
text_at:
        ADD A, [cam]
        ST A, [mcol]
ta_l:   LD A, [X+]
        CMP A, #0
        JZ ta_end
        PUSH X
        PUSH A
        MOV A, B
        CALL map_addr
        CALL to_vram
        POP A
        ST A, [X]
        POP X
        LD A, [mcol]
        INC A
        ST A, [mcol]
        JMP ta_l
ta_end: RET

; X -> 5 characters: n16 in decimal with leading zeros
dec5:   MOV A, XL
        ST A, [dptr]
        MOV A, XH
        ST A, [dptr+1]
        LD A, #0
        ST A, [t3]
d5_l:   LD X, #pow10
        LD A, [t3]
        SHL A
        ADD X, A
        LD A, [X+]
        ST A, [t0]
        LD A, [X]
        ST A, [t1]
        LD B, #'0'
d5_s:   LD A, [n16]
        SUB A, [t0]
        ST A, [t2]
        LD A, [n16+1]
        SBC A, [t1]
        JC d5_d
        ST A, [n16+1]
        LD A, [t2]
        ST A, [n16]
        INC B
        JMP d5_s
d5_d:   LD A, [dptr]
        MOV XL, A
        LD A, [dptr+1]
        MOV XH, A
        ST B, [X+]
        MOV A, XL
        ST A, [dptr]
        MOV A, XH
        ST A, [dptr+1]
        LD A, [t3]
        INC A
        ST A, [t3]
        CMP A, #5
        JNZ d5_l
        RET

; centred message box on row 12
banner: LD A, #28
        LD B, #12
        CALL text_at
        RET

; == tiles ==
; tile 214 = hero mirrored, tile 215 = flag
make_tiles:
        LD A, #0
        ST A, [t0]
mk_l:   LD X, #FONT + 432
        LD A, [t0]
        ADD X, A
        LD A, [X]
        ST A, [t2]
        LD A, #0
        ST A, [t1]
        LD B, #8
mk_b:   LD A, [t2]
        SHR A
        ST A, [t2]
        LD A, [t1]
        ROL A
        ST A, [t1]
        DEC B
        JNZ mk_b
        LD X, #FONT + 3424
        LD A, [t0]
        ADD X, A
        LD A, [t1]
        ST A, [X]
        LD X, #flagbits
        LD A, [t0]
        ADD X, A
        LD B, [X]
        LD X, #FONT + 3440
        LD A, [t0]
        ADD X, A
        ST B, [X]
        LD A, [t0]              ; tiles 216/217: pipe body = rows 4-7 of 23/24 repeated
        AND A, #3
        ADD A, #4
        ST A, [t2]
        LD X, #FONT + 368
        ADD X, A
        LD B, [X]
        LD X, #FONT + 3456
        LD A, [t0]
        ADD X, A
        ST B, [X]
        LD X, #FONT + 384
        LD A, [t2]
        ADD X, A
        LD B, [X]
        LD X, #FONT + 3472
        LD A, [t0]
        ADD X, A
        ST B, [X]
        LD A, [t0]
        INC A
        ST A, [t0]
        CMP A, #16
        JNZ mk_l
        RET

; == data ==
flagbits: .db $C0,$F0,$FC,$FF,$FC,$F0,$C0,$80,$80,$80,$80,$80,$80,$80,$80,$80
pow10:  .dw 10000, 1000, 100, 10, 1
hudbuf: .db "  SCORE 00000  COINS 00000  LIVES 3   WORLD 1-1", 0
t_ouch: .db "      O U C H !       ", 0
t_over: .db " GAME OVER  - ENTER  ", 0
t_clear: .db " COURSE CLEAR - ENTER ", 0

; ground runs: columns, top row (0 = pit)
grounds: .db 50,27, 3,0, 30,27, 4,0, 36,27, 3,0, 40,27, 2,0, 6,25, 2,0, 79,27
; objects: col,row,tile,len,kind (0 tiles 1 pipe 2 walker 3 flag)
objects:
        .db 14,23,21,1,0
        .db 18,23,20,5,0,20,23,21,1,0,20,19,21,1,0
        .db 24,26,0,1,2
        .db 28,25,0,2,1
        .db 36,24,0,3,1
        .db 40,26,0,1,2,44,26,0,1,2
        .db 46,24,0,3,1
        .db 51,20,25,3,0
        .db 60,23,20,3,0,63,19,20,8,0,63,18,25,3,0
        .db 70,26,0,1,2,68,18,0,1,2
        .db 74,23,21,1,0,76,23,20,2,0,78,23,21,1,0
        .db 87,20,25,4,0
        .db 92,26,0,1,2,95,26,0,1,2
        .db 100,24,0,3,1
        .db 106,22,20,4,0,106,21,25,4,0
        .db 112,26,0,1,2
        .db 118,23,21,3,0
        .db 123,20,25,4,0
        .db 130,26,0,1,2,134,26,0,1,2,138,26,0,1,2
        .db 145,24,0,3,1
        .db 152,23,20,6,0,154,19,21,1,0
        .db 160,26,0,1,2,166,26,0,1,2
        .db 172,22,25,4,0
        .db 175,24,1,1,0,176,23,1,1,0,176,24,1,1,0
        .db 177,22,1,1,0,177,23,1,1,0,177,24,1,1,0
        .db 185,24,0,1,2
        .db 193,22,25,5,0
        .db 200,26,0,1,2,204,26,0,1,2
        .db 210,24,0,3,1
        .db 220,26,1,8,0,221,25,1,7,0,222,24,1,6,0,223,23,1,5,0
        .db 224,22,1,4,0,225,21,1,3,0,226,20,1,2,0,227,19,1,1,0
        .db 238,8,0,1,3
        .db 255

state:  .db 0
lives:  .db 3
score:  .dw 0
coins:  .db 0
cam:    .db 0
px:     .db 0
pxf:    .db 0
py:     .db 0
pyf:    .db 0
vy:     .db 0
onground: .db 0
face:   .db 0
nx:     .db 0
nxf:    .db 0
ny:     .db 0
nyf:    .db 0
d_px:   .db 0
d_py:   .db 0
mcol:   .db 0
gcol:   .db 0
run_left: .db 0
run_top: .db 0
runptr: .dw 0
orow:   .db 0
otile:  .db 0
olen:   .db 0
okind:  .db 0
ei:     .db 0
ex:     .db 0
exf:    .db 0
ey:     .db 0
edir:   .db 0
n16:    .dw 0
dptr:   .dw 0
t0:     .db 0
t1:     .db 0
t2:     .db 0
t3:     .db 0
e_on:   .db 0,0,0,0,0,0
e_data: .ds 24
