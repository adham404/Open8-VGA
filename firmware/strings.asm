; Open8-VGA firmware — text
; Author: Adham Elshafei

s_title:    .db " OPEN8-VGA  by Adham Elshafei", 0
s_line:     .db "Line ", 0
s_col:      .db "  Col ", 0
s_free:     .db "  Free ", 0
s_bar:      .db " F1 Help  F2 Assemble  F3 Run  F4 Save  F5 Examples  F6 Load  F9 New", 0
s_long:     .db "Line is full (79 characters).", 0
s_full:     .db "The text buffer is full (16 KB).", 0
s_confirm_new:  .db "Erase all text and start a new program? (Y/N)", 0
s_confirm_load: .db "This replaces the text in the editor. Load it? (Y/N)", 0
s_assembling:   .db "Assembling...", 0
s_asm_ok:   .db "Assembled OK: ", 0
s_asm_ok2:  .db " bytes at $8000. Press F3 to run.", 0
s_err_line: .db "Error in line ", 0
s_violation:    .db "Note: the program tried to write to protected system memory.", 10, 0
s_finished: .db "-- Program finished. Press any key to return to the editor. --", 0
s_reset:    .db "The machine was reset. Your program text is safe.", 0
s_trap:     .db "Invalid instruction at ", 0
s_trap2:    .db " - the program was stopped.", 0
s_help_title:   .db " HELP  page ", 0
s_help_keys:    .db "    PgDn/Space: next   PgUp: back   ESC: editor", 0
s_ex_title: .db " EXAMPLE PROGRAMS", 0
s_ex_prompt:    .db "Press a number to load an example into the editor, or ESC.", 0
s_indent:   .db "   ", 0
s_dot:      .db ". ", 0
s_saved:    .db "Saved ", 0
s_loaded:   .db "Loaded ", 0
s_bytes_slot:   .db " bytes, slot ", 0
s_ee_long:  .db "Too long to save: a slot holds 16380 characters.", 0
s_ee_fail:  .db "EEPROM write failed - the program was NOT saved.", 0
s_ee_none:  .db "No EEPROM found: SAVE/LOAD needs the 25LC512 in socket U_EE.", 0
s_ee_save_t:    .db " SAVE THE PROGRAM TO EEPROM", 0
s_ee_load_t:    .db " LOAD A PROGRAM FROM EEPROM", 0
s_empty:    .db "(empty)", 0
s_lparen:   .db "   (", 0
s_bytes_rp: .db " bytes)", 0
s_ee_prompt:    .db "Press 1-4 to choose a slot, or ESC to go back.", 0
s_ee_overwrite: .db "Replace the program in this slot? (Y/N)", 0
s_ee_saving:    .db "Saving...", 0
s_ee_empty: .db "That slot is empty.", 0

s_welcome:
    .db "Welcome! This computer boots straight into an assembly language editor.", 10, 10
    .db "  1. EDIT      Type your program. Arrows, Home/End, PgUp/PgDn move around.", 10
    .db "  2. ASSEMBLE  Press F2. Mistakes are reported with their line number.", 10
    .db "  3. RUN       Press F3. Your program starts at address $8000.", 10
    .db "  4. STOP      Press the RESET button. Your program text is kept.", 10
    .db "  5. RETURN    End a program with RET (or CALL EXIT) to come back here.", 10, 10
    .db "  F1 opens the built-in help: instructions, registers, syntax, memory map.", 10
    .db "  F5 loads an example program.  F9 starts a new, empty program.", 10
    .db "  F4 saves your program to EEPROM, F6 loads it back (4 slots).", 10, 10
    .db "A small example is already in the editor - press F3 to run it.", 10, 10
    .db "Press any key to start.", 0

s_err0:     .db ": ?", 0
s_err1:     .db ": unknown instruction", 0
s_err2:     .db ": these operands are not valid for this instruction", 0
s_err3:     .db ": undefined name", 0
s_err4:     .db ": name defined twice", 0
s_err5:     .db ": value does not fit in a byte", 0
s_err6:     .db ": program too large (must end before $AF00)", 0
s_err7:     .db ": too many names (192 max)", 0
s_err8:     .db ": syntax error", 0
s_err9:     .db ": bad number", 0
s_err10:    .db ": name longer than 14 characters", 0
s_err11:    .db ": unknown directive", 0
s_err12:    .db ": name must be defined above this line", 0
s_err13:    .db ": reserved word cannot be a label", 0
err_table:  .dw s_err0, s_err1, s_err2, s_err3, s_err4, s_err5, s_err6, s_err7
            .dw s_err8, s_err9, s_err10, s_err11, s_err12, s_err13
