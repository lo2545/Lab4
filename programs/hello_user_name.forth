interrupt: handle_input

variable buf_start
variable buf_len
variable input_done
variable ch_var

: handle_input
    key ch_var !
    ch_var @ 0 =
    if
        1 input_done !
    else
        ch_var @ buf_start @ buf_len @ + !
        buf_len @ 1 + buf_len !
    then
    iret
;

: print_buf
    0
    begin
        dup buf_len @ <
    while
        buf_start @ over + @ emit
        1 +
    repeat
    drop
;

: main
    1024 buf_start !
    0 buf_len !
    0 input_done !
    ." What is your name?"
    10 emit
    begin
        input_done @
    until
    ." Hello, "
    print_buf
    33 emit
    10 emit
    halt
;
