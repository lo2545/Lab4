variable hi
variable lo
variable carry

: d+
    lo @
    swap +
    dup lo !
    swap
    0 <
    if
        1
    else
        0
    then
    carry !
    hi @ carry @ + hi !
;

: main
    0 hi !
    0 lo !
    0 carry !
    1000000000 d+
    1500000000 d+
    hi @ __print_int
    32 emit
    lo @ __print_int
    halt
;
