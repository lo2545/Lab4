variable a0
variable a1
variable a2
variable a3
variable b0
variable b1
variable b2
variable b3
variable r0v
variable r1v
variable r2v
variable r3v

: scalar_add
    a0 @ b0 @ + r0v !
    a1 @ b1 @ + r1v !
    a2 @ b2 @ + r2v !
    a3 @ b3 @ + r3v !
;

: vector_add
    vload,v0,512
    vload,v1,516
    vadd,v2,v0,v1
    vstore,v2,520
;

: print_results
    r0v @ __print_int
    32 emit
    r1v @ __print_int
    32 emit
    r2v @ __print_int
    32 emit
    r3v @ __print_int
    10 emit
;

: main
    10 a0 !   10 512 !
    20 a1 !   20 513 !
    30 a2 !   30 514 !
    40 a3 !   40 515 !
    50 b0 !   50 516 !
    60 b1 !   60 517 !
    70 b2 !   70 518 !
    80 b3 !   80 519 !
    scalar_add
    print_results
    vector_add
    520 @ __print_int
    32 emit
    521 @ __print_int
    32 emit
    522 @ __print_int
    32 emit
    523 @ __print_int
    10 emit
    halt
;
