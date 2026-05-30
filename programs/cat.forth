interrupt: handle_input

variable last_char

: handle_input
    key
    dup last_char !
    emit
    iret
;

: main
    0 last_char !
    begin
        0
    until
;
