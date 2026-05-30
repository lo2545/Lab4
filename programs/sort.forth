variable arr_base
variable arr_len
variable i_var
variable j_var
variable tmp_var
variable ai
variable aj

: wait_key
    begin
        key dup
    until
;

: read_array
    wait_key arr_len !
    0 i_var !
    begin
        i_var @ arr_len @ <
    while
        wait_key
        arr_base @ i_var @ + !
        i_var @ 1 + i_var !
    repeat
;

: bubble_pass
    0 i_var !
    begin
        i_var @ arr_len @ 1 - <
    while
        arr_base @ i_var @ + @ ai !
        arr_base @ i_var @ 1 + + @ aj !
        ai @ aj @ >
        if
            aj @ arr_base @ i_var @ + !
            ai @ arr_base @ i_var @ 1 + + !
        then
        i_var @ 1 + i_var !
    repeat
;

: sort_array
    0 j_var !
    begin
        j_var @ arr_len @ <
    while
        bubble_pass
        j_var @ 1 + j_var !
    repeat
;

: print_array
    0 i_var !
    begin
        i_var @ arr_len @ <
    while
        arr_base @ i_var @ + @ emit
        i_var @ 1 + i_var !
    repeat
;

: main
    256 arr_base !
    read_array
    sort_array
    print_array
    halt
;
