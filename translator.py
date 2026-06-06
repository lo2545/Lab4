import struct
import sys

from isa import (
    DATA_RSTACK_TOP,
    DATA_STACK_TOP,
    INTERRUPT_VECTOR_ADDR,
    IO_IN_ADDR,
    IO_OUT_ADDR,
    Opcode,
    decode,
    encode_i,
    encode_r,
    encode_v,
    mnemonic,
)

SP = 29
RP = 30
TMP0 = 0
TMP1 = 1
TMP2 = 2
TMP3 = 3
TMP4 = 4
TMP5 = 5
TMP6 = 6
TMP7 = 7
TMP8 = 8
TMP9 = 9
TMP10 = 10
TMP11 = 11
TMP12 = 12
ZERO_REG = 13

STATIC_START = 0x0010


class Translator:
    def __init__(self) -> None:
        self.instructions: list[int] = []
        self.data: list[int] = [0] * STATIC_START
        self.static_ptr: int = STATIC_START
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, Opcode, int, int]] = []
        self.word_defs: dict[str, int] = {}
        self.variable_addrs: dict[str, int] = {}
        self.interrupt_handler: str | None = None

    def emit(self, word: int) -> int:
        addr = len(self.instructions)
        self.instructions.append(word)
        return addr

    def alloc_data(self, size: int = 1) -> int:
        addr = self.static_ptr
        for _ in range(size):
            self.data.append(0)
        self.static_ptr += size
        return addr

    def emit_data(self, value: int) -> int:
        addr = self.static_ptr
        self.data.append(value)
        self.static_ptr += 1
        return addr

    def push(self, reg: int) -> None:
        self.emit(encode_i(Opcode.STORE, reg, SP, 0))
        self.emit(encode_i(Opcode.ADDI, SP, SP, -1))

    def pop(self, reg: int) -> None:
        self.emit(encode_i(Opcode.ADDI, SP, SP, 1))
        self.emit(encode_i(Opcode.LOAD, reg, SP, 0))

    def rpush(self, reg: int) -> None:
        self.emit(encode_i(Opcode.STORE, reg, RP, 0))
        self.emit(encode_i(Opcode.ADDI, RP, RP, -1))

    def rpop(self, reg: int) -> None:
        self.emit(encode_i(Opcode.ADDI, RP, RP, 1))
        self.emit(encode_i(Opcode.LOAD, reg, RP, 0))

    def emit_li(self, reg: int, value: int) -> None:
        if -32768 <= value <= 32767:
            self.emit(encode_i(Opcode.LI, reg, 0, value))
        else:
            lower = value & 0xFFFF
            if lower > 32767:
                lower -= 65536
                upper = ((value - lower) >> 16) & 0xFFFF
            else:
                upper = (value >> 16) & 0xFFFF
            self.emit(encode_i(Opcode.LUI, reg, 0, upper))
            if lower != 0:
                self.emit(encode_i(Opcode.ADDI, reg, reg, lower))

    def emit_fixup(self, opcode: Opcode, rd: int, rs1: int, label: str) -> int:
        addr = self.emit(encode_i(opcode, rd, rs1, 0))
        self.fixups.append((addr, label, opcode, rd, rs1))
        return addr

    def cmp_tos_zero(self) -> None:
        self.emit(encode_i(Opcode.LI, ZERO_REG, 0, 0))
        self.emit(encode_r(Opcode.CMP, 0, TMP0, ZERO_REG))

    def compile_string_literal(self, s: str) -> int:
        addr = self.emit_data(len(s))
        for ch in s:
            self.emit_data(ord(ch))
        return addr

    def tokenize(self, src: str) -> list[str]:
        tokens: list[str] = []
        i = 0
        while i < len(src):
            while i < len(src) and src[i] in " \t\n\r":
                i += 1
            if i >= len(src):
                break
            if src[i] == "\\" and (i + 1 >= len(src) or src[i + 1] in " \t\n\r"):
                while i < len(src) and src[i] != "\n":
                    i += 1
                continue
            if src[i] == "(" and (i == 0 or src[i - 1] in " \t\n\r("):
                depth = 1
                i += 1
                while i < len(src) and depth > 0:
                    if src[i] == "(":
                        depth += 1
                    elif src[i] == ")":
                        depth -= 1
                    i += 1
                continue
            if src[i : i + 2] == '."':
                j = i + 2
                while j < len(src) and src[j] == " ":
                    j += 1
                end = src.find('"', j)
                if end == -1:
                    raise ValueError('unterminated ."')
                tokens.append('."' + src[j:end])
                i = end + 1
                continue
            j = i
            while j < len(src) and src[j] not in " \t\n\r":
                j += 1
            tokens.append(src[i:j])
            i = j
        return tokens

    def compile_cmp_bool(self, jump_op: Opcode) -> None:
        fixup_t = self.emit(encode_i(jump_op, 0, 0, 0))
        self.emit(encode_i(Opcode.LI, TMP0, 0, 0))
        fixup_e = self.emit(encode_i(Opcode.JMP, 0, 0, 0))
        t_addr = len(self.instructions)
        self.emit(encode_i(Opcode.LI, TMP0, 0, 1))
        e_addr = len(self.instructions)
        self.instructions[fixup_t] = encode_i(jump_op, 0, 0, t_addr)
        self.instructions[fixup_e] = encode_i(Opcode.JMP, 0, 0, e_addr)

    def compile_tokens(self, tokens: list[str]) -> None:
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            i += 1

            if tok == ":":
                name = tokens[i]
                i += 1
                self.labels[name] = len(self.instructions)
                self.word_defs[name] = len(self.instructions)
                body: list[str] = []
                depth = 1
                while i < len(tokens):
                    t = tokens[i]
                    i += 1
                    if t == ":":
                        depth += 1
                        body.append(t)
                    elif t == ";" and depth == 1:
                        break
                    elif t == ";":
                        depth -= 1
                        body.append(t)
                    else:
                        body.append(t)
                self.compile_tokens(body)
                self.emit(encode_i(Opcode.RET, 0, 0, 0))
                continue

            if tok == "interrupt:":
                self.interrupt_handler = tokens[i]
                i += 1
                continue

            if tok == "variable":
                name = tokens[i]
                i += 1
                addr = self.alloc_data(1)
                self.variable_addrs[name] = addr
                continue

            if tok == "if":
                self.pop(TMP0)
                self.cmp_tos_zero()
                fixup_jz = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
                body_if: list[str] = []
                body_else: list[str] = []
                in_else = False
                depth2 = 1
                while i < len(tokens):
                    t = tokens[i]
                    i += 1
                    if t == "if":
                        depth2 += 1
                        (body_else if in_else else body_if).append(t)
                    elif t == "else" and depth2 == 1:
                        in_else = True
                    elif t == "then" and depth2 == 1:
                        break
                    elif t == "then":
                        depth2 -= 1
                        (body_else if in_else else body_if).append(t)
                    else:
                        (body_else if in_else else body_if).append(t)
                self.compile_tokens(body_if)
                if body_else:
                    fixup_jmp = self.emit(encode_i(Opcode.JMP, 0, 0, 0))
                    else_start = len(self.instructions)
                    self.instructions[fixup_jz] = encode_i(Opcode.JZ, 0, 0, else_start)
                    self.compile_tokens(body_else)
                    end_addr = len(self.instructions)
                    self.instructions[fixup_jmp] = encode_i(Opcode.JMP, 0, 0, end_addr)
                else:
                    end_addr = len(self.instructions)
                    self.instructions[fixup_jz] = encode_i(Opcode.JZ, 0, 0, end_addr)
                continue

            if tok == "begin":
                begin_addr = len(self.instructions)
                loop_body: list[str] = []
                while i < len(tokens) and tokens[i] not in ("until", "while"):
                    loop_body.append(tokens[i])
                    i += 1
                kind = tokens[i]
                i += 1
                self.compile_tokens(loop_body)
                if kind == "until":
                    self.pop(TMP0)
                    self.cmp_tos_zero()
                    self.emit(encode_i(Opcode.JZ, 0, 0, begin_addr))
                else:
                    self.pop(TMP0)
                    self.cmp_tos_zero()
                    fixup_exit = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
                    repeat_body: list[str] = []
                    while i < len(tokens) and tokens[i] != "repeat":
                        repeat_body.append(tokens[i])
                        i += 1
                    i += 1
                    self.compile_tokens(repeat_body)
                    self.emit(encode_i(Opcode.JMP, 0, 0, begin_addr))
                    end_addr = len(self.instructions)
                    self.instructions[fixup_exit] = encode_i(Opcode.JZ, 0, 0, end_addr)
                continue

            if tok == "do":
                idx_r = TMP4
                lim_r = TMP5
                self.pop(idx_r)
                self.pop(lim_r)
                do_start = len(self.instructions)
                do_body: list[str] = []
                while i < len(tokens) and tokens[i] != "loop":
                    do_body.append(tokens[i])
                    i += 1
                i += 1
                self.compile_tokens(do_body)
                self.emit(encode_i(Opcode.ADDI, idx_r, idx_r, 1))
                self.emit(encode_r(Opcode.CMP, 0, idx_r, lim_r))
                self.emit(encode_i(Opcode.JN, 0, 0, do_start))
                continue

            if tok == "i":
                self.push(TMP4)
                continue

            if tok.startswith('."'):
                s = tok[2:]
                str_addr = self.compile_string_literal(s)
                self.emit(encode_i(Opcode.LI, TMP0, 0, str_addr))
                self.push(TMP0)
                self.emit_fixup(Opcode.CALL, 0, 0, "__print_pstr")
                continue

            if tok == "emit":
                self.pop(TMP0)
                self.emit(encode_i(Opcode.LI, TMP1, 0, IO_OUT_ADDR))
                self.emit(encode_i(Opcode.STORE, TMP0, TMP1, 0))
                continue

            if tok == "key":
                self.emit(encode_i(Opcode.LI, TMP0, 0, IO_IN_ADDR))
                self.emit(encode_i(Opcode.LOAD, TMP0, TMP0, 0))
                self.push(TMP0)
                continue

            if tok == "@":
                self.pop(TMP0)
                self.emit(encode_i(Opcode.LOAD, TMP0, TMP0, 0))
                self.push(TMP0)
                continue

            if tok == "!":
                self.pop(TMP0)
                self.pop(TMP1)
                self.emit(encode_i(Opcode.STORE, TMP1, TMP0, 0))
                continue

            if tok == "+":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.ADD, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "-":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.SUB, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "*":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.MUL, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "/":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.DIV, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "mod":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.MOD, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "and":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.AND, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "or":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.OR, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "xor":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.XOR, TMP0, TMP0, TMP1))
                self.push(TMP0)
                continue

            if tok == "dup":
                self.pop(TMP0)
                self.push(TMP0)
                self.push(TMP0)
                continue

            if tok == "drop":
                self.pop(TMP0)
                continue

            if tok == "swap":
                self.pop(TMP0)
                self.pop(TMP1)
                self.push(TMP0)
                self.push(TMP1)
                continue

            if tok == "over":
                self.pop(TMP0)
                self.pop(TMP1)
                self.push(TMP1)
                self.push(TMP0)
                self.push(TMP1)
                continue

            if tok == "rot":
                self.pop(TMP0)
                self.pop(TMP1)
                self.pop(TMP2)
                self.push(TMP1)
                self.push(TMP0)
                self.push(TMP2)
                continue

            if tok == "nip":
                self.pop(TMP0)
                self.pop(TMP1)
                self.push(TMP0)
                continue

            if tok == "2dup":
                self.pop(TMP0)
                self.pop(TMP1)
                self.push(TMP1)
                self.push(TMP0)
                self.push(TMP1)
                self.push(TMP0)
                continue

            if tok == "2drop":
                self.pop(TMP0)
                self.pop(TMP0)
                continue

            if tok == "=":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.CMP, 0, TMP0, TMP1))
                self.compile_cmp_bool(Opcode.JZ)
                self.push(TMP0)
                continue

            if tok == "<":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.CMP, 0, TMP0, TMP1))
                self.compile_cmp_bool(Opcode.JN)
                self.push(TMP0)
                continue

            if tok == ">":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.CMP, 0, TMP1, TMP0))
                self.compile_cmp_bool(Opcode.JN)
                self.push(TMP0)
                continue

            if tok == "<=":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.CMP, 0, TMP0, TMP1))
                fixup_n = self.emit(encode_i(Opcode.JN, 0, 0, 0))
                fixup_z = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
                self.emit(encode_i(Opcode.LI, TMP0, 0, 0))
                fixup_e = self.emit(encode_i(Opcode.JMP, 0, 0, 0))
                t_addr = len(self.instructions)
                self.emit(encode_i(Opcode.LI, TMP0, 0, 1))
                e_addr = len(self.instructions)
                self.instructions[fixup_n] = encode_i(Opcode.JN, 0, 0, t_addr)
                self.instructions[fixup_z] = encode_i(Opcode.JZ, 0, 0, t_addr)
                self.instructions[fixup_e] = encode_i(Opcode.JMP, 0, 0, e_addr)
                self.push(TMP0)
                continue

            if tok == ">=":
                self.pop(TMP1)
                self.pop(TMP0)
                self.emit(encode_r(Opcode.CMP, 0, TMP1, TMP0))
                fixup_n = self.emit(encode_i(Opcode.JN, 0, 0, 0))
                fixup_z = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
                self.emit(encode_i(Opcode.LI, TMP0, 0, 0))
                fixup_e = self.emit(encode_i(Opcode.JMP, 0, 0, 0))
                t_addr = len(self.instructions)
                self.emit(encode_i(Opcode.LI, TMP0, 0, 1))
                e_addr = len(self.instructions)
                self.instructions[fixup_n] = encode_i(Opcode.JN, 0, 0, t_addr)
                self.instructions[fixup_z] = encode_i(Opcode.JZ, 0, 0, t_addr)
                self.instructions[fixup_e] = encode_i(Opcode.JMP, 0, 0, e_addr)
                self.push(TMP0)
                continue

            if tok == "0=":
                self.pop(TMP0)
                self.cmp_tos_zero()
                self.compile_cmp_bool(Opcode.JZ)
                self.push(TMP0)
                continue

            if tok == "not":
                self.pop(TMP0)
                self.cmp_tos_zero()
                self.compile_cmp_bool(Opcode.JZ)
                self.push(TMP0)
                continue

            if tok == ">r":
                self.pop(TMP0)
                self.rpush(TMP0)
                continue

            if tok == "r>":
                self.rpop(TMP0)
                self.push(TMP0)
                continue

            if tok == "r@":
                self.emit(encode_i(Opcode.ADDI, TMP0, RP, 1))
                self.emit(encode_i(Opcode.LOAD, TMP0, TMP0, 0))
                self.push(TMP0)
                continue
            if tok == "halt":
                self.emit(encode_i(Opcode.HALT, 0, 0, 0))
                continue

            if tok == "iret":
                self.emit(encode_i(Opcode.IRET, 0, 0, 0))
                continue

            vec_ops: dict[str, Opcode] = {
                "vadd": Opcode.VADD,
                "vsub": Opcode.VSUB,
                "vmul": Opcode.VMUL,
                "vdiv": Opcode.VDIV,
                "vcmp": Opcode.VCMP,
            }
            parts = tok.split(",")
            if parts[0] in vec_ops and len(parts) == 4:
                vd = int(parts[1][-1])
                vs1 = int(parts[2][-1])
                vs2 = int(parts[3][-1])
                self.emit(encode_v(vec_ops[parts[0]], vd, vs1, vs2))
                continue
            if parts[0] == "vload" and len(parts) == 3:
                vd = int(parts[1][-1])
                self.emit(encode_i(Opcode.LI, TMP0, 0, int(parts[2])))
                self.emit(encode_v(Opcode.VLOAD, vd, 0, TMP0))
                continue
            if parts[0] == "vstore" and len(parts) == 3:
                vd = int(parts[1][-1])
                self.emit(encode_i(Opcode.LI, TMP0, 0, int(parts[2])))
                self.emit(encode_v(Opcode.VSTORE, vd, 0, TMP0))
                continue

            if tok.lstrip("-").isdigit():
                self.emit_li(TMP0, int(tok))
                self.push(TMP0)
                continue

            if tok in self.variable_addrs:
                self.emit(encode_i(Opcode.LI, TMP0, 0, self.variable_addrs[tok]))
                self.push(TMP0)
                continue

            self.emit_fixup(Opcode.CALL, 0, 0, tok)

    def add_builtins(self) -> None:
        self.labels["__print_pstr"] = len(self.instructions)
        ptr_r = TMP6
        len_r = TMP7
        idx_r = TMP8
        ch_r = TMP9
        out_r = TMP10
        self.pop(ptr_r)
        self.emit(encode_i(Opcode.LOAD, len_r, ptr_r, 0))
        self.emit(encode_i(Opcode.LI, idx_r, 0, 0))
        self.emit(encode_i(Opcode.LI, out_r, 0, IO_OUT_ADDR))
        loop = len(self.instructions)
        self.emit(encode_r(Opcode.CMP, 0, idx_r, len_r))
        fixup_end = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
        self.emit(encode_r(Opcode.ADD, TMP0, ptr_r, idx_r))
        self.emit(encode_i(Opcode.ADDI, TMP0, TMP0, 1))
        self.emit(encode_i(Opcode.LOAD, ch_r, TMP0, 0))
        self.emit(encode_i(Opcode.STORE, ch_r, out_r, 0))
        self.emit(encode_i(Opcode.ADDI, idx_r, idx_r, 1))
        self.emit(encode_i(Opcode.JMP, 0, 0, loop))
        end = len(self.instructions)
        self.instructions[fixup_end] = encode_i(Opcode.JZ, 0, 0, end)
        self.emit(encode_i(Opcode.RET, 0, 0, 0))

        self.labels["__print_int"] = len(self.instructions)
        n_r = TMP6
        div_r = TMP7
        rem_r = TMP8
        neg_r = TMP9
        out_r2 = TMP10
        buf_r = TMP11
        cnt_r = TMP12
        self.pop(n_r)
        self.emit(encode_i(Opcode.LI, out_r2, 0, IO_OUT_ADDR))
        self.emit(encode_i(Opcode.LI, neg_r, 0, 0))
        self.emit(encode_i(Opcode.LI, ZERO_REG, 0, 0))
        self.emit(encode_r(Opcode.CMP, 0, n_r, ZERO_REG))
        fixup_is_neg = self.emit(encode_i(Opcode.JN, 0, 0, 0))
        neg_start = len(self.instructions)
        fixup_is_neg2 = self.emit(encode_i(Opcode.JMP, 0, 0, 0))
        after_neg2 = len(self.instructions)
        self.instructions[fixup_is_neg] = encode_i(Opcode.JN, 0, 0, neg_start)
        self.instructions[fixup_is_neg2] = encode_i(Opcode.JMP, 0, 0, after_neg2)
        neg_start = len(self.instructions)
        self.emit(encode_i(Opcode.LI, neg_r, 0, 1))
        self.emit(encode_r(Opcode.SUB, n_r, ZERO_REG, n_r))
        after_neg = len(self.instructions)
        self.instructions[fixup_is_neg] = encode_i(Opcode.JN, 0, 0, neg_start)
        self.instructions[fixup_is_neg2] = encode_i(Opcode.JMP, 0, 0, after_neg)
        self.emit(encode_i(Opcode.LI, buf_r, 0, 0x0300))
        self.emit(encode_i(Opcode.LI, cnt_r, 0, 0))
        self.emit(encode_i(Opcode.LI, div_r, 0, 10))
        dloop = len(self.instructions)
        self.emit(encode_r(Opcode.MOD, rem_r, n_r, div_r))
        self.emit(encode_i(Opcode.ADDI, rem_r, rem_r, 48))
        self.emit(encode_r(Opcode.ADD, TMP0, buf_r, cnt_r))
        self.emit(encode_i(Opcode.STORE, rem_r, TMP0, 0))
        self.emit(encode_i(Opcode.ADDI, cnt_r, cnt_r, 1))
        self.emit(encode_r(Opcode.DIV, n_r, n_r, div_r))
        self.emit(encode_r(Opcode.CMP, 0, n_r, ZERO_REG))
        self.emit(encode_i(Opcode.JNZ, 0, 0, dloop))
        self.emit(encode_r(Opcode.CMP, 0, neg_r, ZERO_REG))
        fixup_skip_minus = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
        self.emit(encode_i(Opcode.LI, TMP0, 0, 45))
        self.emit(encode_i(Opcode.STORE, TMP0, out_r2, 0))
        after_minus = len(self.instructions)
        self.instructions[fixup_skip_minus] = encode_i(Opcode.JZ, 0, 0, after_minus)
        self.emit(encode_i(Opcode.ADDI, cnt_r, cnt_r, -1))
        ploop = len(self.instructions)
        self.emit(encode_r(Opcode.ADD, TMP0, buf_r, cnt_r))
        self.emit(encode_i(Opcode.LOAD, TMP0, TMP0, 0))
        self.emit(encode_i(Opcode.STORE, TMP0, out_r2, 0))
        self.emit(encode_r(Opcode.CMP, 0, cnt_r, ZERO_REG))
        fixup_pdone = self.emit(encode_i(Opcode.JZ, 0, 0, 0))
        self.emit(encode_i(Opcode.ADDI, cnt_r, cnt_r, -1))
        self.emit(encode_i(Opcode.JMP, 0, 0, ploop))
        pdone = len(self.instructions)
        self.instructions[fixup_pdone] = encode_i(Opcode.JZ, 0, 0, pdone)
        self.emit(encode_i(Opcode.RET, 0, 0, 0))

    def translate(self, src: str) -> tuple[list[int], list[int]]:
        entry_jmp = self.emit(encode_i(Opcode.JMP, 0, 0, 0))
        ivec_slot = self.emit(encode_i(Opcode.LI, 0, 0, 0))

        tokens = self.tokenize(src)
        self.add_builtins()
        self.compile_tokens(tokens)

        if "main" not in self.labels:
            raise ValueError("no 'main' word defined")

        self.instructions[entry_jmp] = encode_i(Opcode.JMP, 0, 0, self.labels["main"])

        handler_addr = 0
        if self.interrupt_handler and self.interrupt_handler in self.labels:
            handler_addr = self.labels[self.interrupt_handler]
        self.instructions[ivec_slot] = encode_i(Opcode.LI, 0, 0, handler_addr)

        for fix_addr, label, opcode, rd, rs1 in self.fixups:
            if label not in self.labels:
                raise ValueError(f"undefined label: {label}")
            self.instructions[fix_addr] = encode_i(opcode, rd, rs1, self.labels[label])

        while len(self.data) <= DATA_STACK_TOP:
            self.data.append(0)
        while len(self.data) <= DATA_RSTACK_TOP:
            self.data.append(0)

        self.data[INTERRUPT_VECTOR_ADDR] = handler_addr

        return self.instructions, self.data


def write_binary(instructions: list[int], data: list[int], bin_path: str, dbg_path: str) -> None:
    with open(bin_path, "wb") as f:
        f.write(struct.pack(">I", len(instructions)))
        for word in instructions:
            f.write(struct.pack(">I", word & 0xFFFFFFFF))
        f.write(struct.pack(">I", len(data)))
        for word in data:
            f.write(struct.pack(">I", word & 0xFFFFFFFF))

    with open(dbg_path, "w") as f:
        f.write("=== INSTRUCTION MEMORY ===\n")
        for addr, word in enumerate(instructions):
            try:
                instr = decode(word)
                mn = mnemonic(instr)
            except Exception:
                mn = "???"
            f.write(f"{addr:04x} - {word:08X} - {mn}\n")
        f.write("\n=== DATA MEMORY ===\n")
        for addr, word in enumerate(data):
            f.write(f"{addr:04x} - {word:08X}\n")


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: translator.py <source.forth> <output.bin> [output.dbg]")
        sys.exit(1)
    src_path = sys.argv[1]
    bin_path = sys.argv[2]
    dbg_path = sys.argv[3] if len(sys.argv) > 3 else bin_path + ".dbg"

    with open(src_path) as f:
        src = f.read()

    t = Translator()
    instructions, data = t.translate(src)
    write_binary(instructions, data, bin_path, dbg_path)
    print(f"translated: {len(instructions)} instructions, {len(data)} data words")
    print(f"binary: {bin_path}")
    print(f"debug:  {dbg_path}")


if __name__ == "__main__":
    main()
