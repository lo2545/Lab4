from enum import IntEnum

DATA_MEM_SIZE = 0x10000
INSTR_MEM_SIZE = 0x10000
INTERRUPT_VECTOR_ADDR = 0x0001
IO_IN_ADDR = 0xFFFE
IO_OUT_ADDR = 0xFFFF
DATA_STATIC_START = 0x0000
DATA_STACK_TOP = 0x01FF
DATA_RSTACK_TOP = 0x02FF
VECTOR_SIZE = 4
WORD_SIZE = 32

class Opcode(IntEnum):
    ADD = 0
    SUB = 1
    MUL = 2
    DIV = 3
    MOD = 4
    AND = 5
    OR = 6
    XOR = 7
    SHL = 8
    SHR = 9
    CMP = 10
    MOV = 11
    LI = 12
    ADDI = 13
    LOAD = 14
    STORE = 15
    JMP = 16
    JZ = 17
    JNZ = 18
    JN = 19
    CALL = 20
    RET = 21
    HALT = 22
    IRET = 23
    VADD = 24
    VSUB = 25
    VMUL = 26
    VDIV = 27
    VCMP = 28
    VLOAD = 29
    VSTORE = 30
    LUI = 31


class InstrType(IntEnum):
    R = 0
    IMM = 1
    VEC = 2


OPCODE_TYPE: dict[Opcode, InstrType] = {
    Opcode.ADD: InstrType.R,
    Opcode.SUB: InstrType.R,
    Opcode.MUL: InstrType.R,
    Opcode.DIV: InstrType.R,
    Opcode.MOD: InstrType.R,
    Opcode.AND: InstrType.R,
    Opcode.OR: InstrType.R,
    Opcode.XOR: InstrType.R,
    Opcode.SHL: InstrType.R,
    Opcode.SHR: InstrType.R,
    Opcode.CMP: InstrType.R,
    Opcode.MOV: InstrType.R,
    Opcode.LI: InstrType.IMM,
    Opcode.LUI: InstrType.IMM,
    Opcode.ADDI: InstrType.IMM,
    Opcode.LOAD: InstrType.IMM,
    Opcode.STORE: InstrType.IMM,
    Opcode.JMP: InstrType.IMM,
    Opcode.JZ: InstrType.IMM,
    Opcode.JNZ: InstrType.IMM,
    Opcode.JN: InstrType.IMM,
    Opcode.CALL: InstrType.IMM,
    Opcode.RET: InstrType.IMM,
    Opcode.HALT: InstrType.IMM,
    Opcode.IRET: InstrType.IMM,
    Opcode.VADD: InstrType.VEC,
    Opcode.VSUB: InstrType.VEC,
    Opcode.VMUL: InstrType.VEC,
    Opcode.VDIV: InstrType.VEC,
    Opcode.VCMP: InstrType.VEC,
    Opcode.VLOAD: InstrType.VEC,
    Opcode.VSTORE: InstrType.VEC,
}


def encode_r(opcode: Opcode, rd: int, rs1: int, rs2: int) -> int:
    return (int(opcode) << 26) | (rd << 21) | (rs1 << 16) | (rs2 << 11)


def encode_i(opcode: Opcode, rd: int, rs1: int, imm: int) -> int:
    return (int(opcode) << 26) | (rd << 21) | (rs1 << 16) | (imm & 0xFFFF)


def encode_v(opcode: Opcode, vd: int, vs1: int, vs2: int) -> int:
    return (int(opcode) << 26) | (vd << 24) | (vs1 << 22) | (vs2 << 20)


def decode(word: int) -> dict[str, object]:
    opcode = Opcode((word >> 26) & 0x3F)
    itype = OPCODE_TYPE[opcode]
    if itype == InstrType.R:
        return {
            "opcode": opcode,
            "type": itype,
            "rd": (word >> 21) & 0x1F,
            "rs1": (word >> 16) & 0x1F,
            "rs2": (word >> 11) & 0x1F,
        }
    if itype == InstrType.IMM:
        raw_imm = word & 0xFFFF
        imm = raw_imm if raw_imm < 0x8000 else raw_imm - 0x10000
        return {
            "opcode": opcode,
            "type": itype,
            "rd": (word >> 21) & 0x1F,
            "rs1": (word >> 16) & 0x1F,
            "imm": imm,
        }
    return {
        "opcode": opcode,
        "type": itype,
        "vd": (word >> 24) & 0x3,
        "vs1": (word >> 22) & 0x3,
        "vs2": (word >> 20) & 0x3,
    }


def mnemonic(instr: dict[str, object]) -> str:
    op = instr["opcode"]
    assert isinstance(op, Opcode)
    itype = instr["type"]
    name = op.name.lower()
    if itype == InstrType.R:
        if op == Opcode.CMP:
            return f"cmp r{instr['rs1']}, r{instr['rs2']}"
        if op == Opcode.MOV:
            return f"mov r{instr['rd']}, r{instr['rs1']}"
        return f"{name} r{instr['rd']}, r{instr['rs1']}, r{instr['rs2']}"
    if itype == InstrType.IMM:
        if op in (Opcode.RET, Opcode.HALT, Opcode.IRET):
            return name
        if op == Opcode.LUI:
            return f"lui r{instr['rd']}, {instr['imm']}"
        if op == Opcode.JMP:
            return f"jmp {instr['imm']}"
        if op in (Opcode.JZ, Opcode.JNZ, Opcode.JN):
            return f"{name} r0, {instr['imm']}"
        if op == Opcode.CALL:
            return f"call {instr['imm']}"
        if op == Opcode.LI:
            return f"li r{instr['rd']}, {instr['imm']}"
        if op == Opcode.ADDI:
            return f"addi r{instr['rd']}, r{instr['rs1']}, {instr['imm']}"
        if op == Opcode.LOAD:
            return f"load r{instr['rd']}, {instr['imm']}(r{instr['rs1']})"
        if op == Opcode.STORE:
            return f"store r{instr['rd']}, {instr['imm']}(r{instr['rs1']})"
    if itype == InstrType.VEC:
        if op in (Opcode.VLOAD, Opcode.VSTORE):
            return f"{name} v{instr['vd']}, {instr['vs1']}(r{instr['vs2']})"
        return f"{name} v{instr['vd']}, v{instr['vs1']}, v{instr['vs2']}"
    return name
