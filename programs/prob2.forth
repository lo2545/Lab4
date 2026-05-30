interrupt: handle_input

variable limit
variable input_done

: handle_input
    key
    dup 10 =
    if
        drop
        1 input_done !
    else
        dup 0 =
        if
            drop
            1 input_done !
        else
            48 -
            limit @ 10 * + limit !
        then
    then
    iret
;

variable fib_a
variable fib_b
variable fib_tmp
variable fib_sum

: even?
    2 mod 0 =
;

: fib_step
    fib_b @ fib_tmp !
    fib_a @ fib_b @ + fib_b !
    fib_tmp @ fib_a !
;

: check_add
    fib_b @ even?
    if
        fib_sum @ fib_b @ + fib_sum !
    then
;

: done?
    fib_b @ limit @ <
    not
;

: main
    0 limit !
    0 input_done !
    begin
        input_done @
    until
    1 fib_a !
    2 fib_b !
    2 fib_sum !
    begin
        fib_step
        check_add
        done?
    until
    fib_sum @ __print_int
    halt
;
