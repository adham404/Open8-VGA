; HELLO - print a message and return to the editor.
; Press F3 to assemble and run. Change the text and run it again!

start:  CALL CLS            ; clear the screen
        LD X, #message      ; X points at the text
        CALL PRINT          ; print until the 0 byte
        RET                 ; back to the editor

message:
        .db "Hello from Open8-VGA!", 10
        .db "This text was printed by your program.", 10, 0
