import struct
import sys
from typing import TextIO, cast

from isa import (
    DATA_MEM_SIZE,
    DATA_RSTACK_TOP,
    DATA_STACK_TOP,
    INSTR_MEM_SIZE,
    INTERRUPT_VECTOR_ADDR,
    IO_IN_ADDR,
    IO_OUT_ADDR,
    VECTOR_SIZE,
    InstrType,
    Opcode,
    decode,
    mnemonic,
)

SP = 29
RP = 30
MAX_TICKS = 10_000_000
LOG_LIMIT = 500

class HaltException(Exception):
    pass


class DataPath:
    def __init__(self, instr_mem: list[int], data_mem: list[int]) -> None:
        self.instr_mem: list[int] = instr_mem + [0] * (INSTR_MEM_SIZE - len(instr_mem))
        self.data_mem: list[int] = data_mem + [0] * (DATA_MEM_SIZE - len(data_mem))
        self.regs: list[int] = [0] * 32
        self.regs[SP] = DATA_STACK_TOP
        self.regs[RP] = DATA_RSTACK_TOP
        self.pc: int = 0
        self.flag_z: bool = False
        self.flag_n: bool = False
        self.vregs: list[list[int]] = [[0] * VECTOR_SIZE for _ in range(4)]
        self.output_buffer: list[str] = []

    def mem_read(self, addr: int) -> int:
        a = addr & 0xFFFF
        val = self.data_mem[a]
        if a == 0xFFFE:
            self.data_mem[a] = 0
        return val

    def mem_write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        v = value & 0xFFFFFFFF
        if v >= 0x80000000:
            v -= 0x100000000
        self.data_mem[addr] = v
        if addr == IO_OUT_ADDR:
            self.output_buffer.append(chr(v & 0xFF))

    def set_flags(self, result: int) -> None:
        self.flag_z = (result & 0xFFFFFFFF) == 0
        self.flag_n = bool((result >> 31) & 1)

    def get_reg(self, idx: int) -> int:
        return self.regs[idx]

    def set_reg(self, idx: int, value: int) -> None:
        v = value & 0xFFFFFFFF
        if v >= 0x80000000:
            v -= 0x100000000
        self.regs[idx] = v


class ControlUnit:
    def __init__(self, dp: DataPath, input_schedule: list[tuple[int, str]]) -> None:
        self.dp = dp
        self.input_schedule: list[tuple[int, str]] = sorted(input_schedule, key=lambda x: x[0])
        self.input_idx: int = 0
        self.tick_count: int = 0
        self.in_interrupt: bool = False
        self.saved_pc: int = 0
        self.log_lines: list[str] = []

    def tick(self) -> None:
        self.tick_count += 1

    def check_interrupt(self) -> None:
        if self.in_interrupt:
            return
        while self.input_idx < len(self.input_schedule):
            t, ch = self.input_schedule[self.input_idx]
            if t > self.tick_count:
                break
            self.dp.data_mem[IO_IN_ADDR] = ord(ch)
            self.input_idx += 1
            handler_addr = self.dp.data_mem[INTERRUPT_VECTOR_ADDR]
            if handler_addr != 0:
                self.saved_pc = self.dp.pc
                self.in_interrupt = True
                self.dp.pc = handler_addr
                self.log_lines.append(
                    f"  [INTERRUPT tick={self.tick_count}] char={repr(ch)} -> handler@{handler_addr:04x}"
                )
                return

    def fetch_decode(self) -> dict[str, object]:
        word = self.dp.instr_mem[self.dp.pc]
        self.dp.pc += 1
        self.tick()
        return decode(word)

    def log_state(self, instr: dict[str, object]) -> None:
        mn = mnemonic(instr)
        r = self.dp.regs
        isr = " [ISR]" if self.in_interrupt else "      "
        self.log_lines.append(
            f"tick={self.tick_count}{isr} pc={self.dp.pc - 1:04x} | {mn:<32} |"
            f" r0={r[0]} r1={r[1]} r2={r[2]} r3={r[3]}"
            f" sp={r[SP]} rp={r[RP]} Z={int(self.dp.flag_z)} N={int(self.dp.flag_n)}"
        )

    def execute(self, instr: dict[str, object]) -> None:
        op = instr["opcode"]
        itype = instr["type"]
        dp = self.dp

        if itype == InstrType.R:
            rd = cast(int, instr["rd"])
            rs1 = cast(int, instr["rs1"])
            rs2 = cast(int, instr["rs2"])
            a = dp.get_reg(rs1)
            b = dp.get_reg(rs2)
            if op == Opcode.ADD:
                dp.set_reg(rd, a + b)
            elif op == Opcode.SUB:
                dp.set_reg(rd, a - b)
                dp.set_flags(a - b)
            elif op == Opcode.MUL:
                dp.set_reg(rd, a * b)
            elif op == Opcode.DIV:
                dp.set_reg(rd, int(a / b) if b != 0 else 0)
            elif op == Opcode.MOD:
                dp.set_reg(rd, a % b if b != 0 else 0)
            elif op == Opcode.AND:
                dp.set_reg(rd, a & b)
            elif op == Opcode.OR:
                dp.set_reg(rd, a | b)
            elif op == Opcode.XOR:
                dp.set_reg(rd, a ^ b)
            elif op == Opcode.SHL:
                dp.set_reg(rd, a << (b & 31))
            elif op == Opcode.SHR:
                dp.set_reg(rd, a >> (b & 31))
            elif op == Opcode.CMP:
                dp.set_flags(a - b)
            elif op == Opcode.MOV:
                dp.set_reg(rd, a)
            self.tick()


        elif itype == InstrType.IMM:
            rd = cast(int, instr["rd"])
            rs1 = cast(int, instr["rs1"])
            imm = cast(int, instr["imm"])
            if op == Opcode.LI:
                dp.set_reg(rd, imm)
            elif op == Opcode.LUI:
                dp.set_reg(rd, imm << 16)
            elif op == Opcode.ADDI:
                dp.set_reg(rd, dp.get_reg(rs1) + imm)
            elif op == Opcode.LOAD:
                dp.set_reg(rd, dp.mem_read(dp.get_reg(rs1) + imm))
            elif op == Opcode.STORE:
                dp.mem_write(dp.get_reg(rs1) + imm, dp.get_reg(rd))
            elif op == Opcode.JMP:
                dp.pc = imm
            elif op == Opcode.JZ:
                if dp.flag_z:
                    dp.pc = imm
            elif op == Opcode.JNZ:
                if not dp.flag_z:
                    dp.pc = imm
            elif op == Opcode.JN:
                if dp.flag_n:
                    dp.pc = imm
            elif op == Opcode.CALL:
                ret_addr = dp.pc
                dp.regs[RP] -= 1
                dp.data_mem[dp.regs[RP]] = ret_addr
                dp.pc = imm
            elif op == Opcode.RET:
                ret_addr = dp.data_mem[dp.regs[RP]]
                dp.regs[RP] += 1
                dp.pc = ret_addr
            elif op == Opcode.HALT:
                raise HaltException
            elif op == Opcode.IRET:
                self.in_interrupt = False
                dp.pc = self.saved_pc
                self.log_lines.append(f"  [IRET tick={self.tick_count}] returning to pc={self.saved_pc:04x}")
            self.tick()


        elif itype == InstrType.VEC:
            vd = cast(int, instr["vd"])
            vs1 = cast(int, instr["vs1"])
            vs2 = cast(int, instr["vs2"])
            if op == Opcode.VADD:
                dp.vregs[vd] = [dp.vregs[vs1][k] + dp.vregs[vs2][k] for k in range(VECTOR_SIZE)]
            elif op == Opcode.VSUB:
                dp.vregs[vd] = [dp.vregs[vs1][k] - dp.vregs[vs2][k] for k in range(VECTOR_SIZE)]
            elif op == Opcode.VMUL:
                dp.vregs[vd] = [dp.vregs[vs1][k] * dp.vregs[vs2][k] for k in range(VECTOR_SIZE)]
            elif op == Opcode.VDIV:
                dp.vregs[vd] = [
                    dp.vregs[vs1][k] // dp.vregs[vs2][k] if dp.vregs[vs2][k] != 0 else 0
                    for k in range(VECTOR_SIZE)
                ]
            elif op == Opcode.VCMP:
                dp.vregs[vd] = [1 if dp.vregs[vs1][k] == dp.vregs[vs2][k] else 0 for k in range(VECTOR_SIZE)]
            elif op == Opcode.VLOAD:
                base = dp.get_reg(vs2) + vs1
                dp.vregs[vd] = [dp.mem_read(base + k) for k in range(VECTOR_SIZE)]
            elif op == Opcode.VSTORE:
                base = dp.get_reg(vs2) + vs1
                for k in range(VECTOR_SIZE):
                    dp.mem_write(base + k, dp.vregs[vd][k])
            self.tick()

    def run(self, log_out: TextIO | None = None) -> None:
        try:
            while self.tick_count < MAX_TICKS:
                self.check_interrupt()
                instr = self.fetch_decode()
                self.log_state(instr)
                self.execute(instr)
        except HaltException:
            self.log_lines.append(f"  [HALT tick={self.tick_count}]")

        if log_out:
            if len(self.log_lines) > LOG_LIMIT:
                self.log_lines = self.log_lines[:LOG_LIMIT]
                self.log_lines.append(f"  [LOG TRUNCATED at {LOG_LIMIT} lines]")
            output = "".join(self.dp.output_buffer)
            self.log_lines.append(f"\n=== OUTPUT ({len(output)} chars) ===")
            self.log_lines.append(output)
            log_out.write("\n".join(self.log_lines) + "\n")

    def get_output(self) -> str:
        return "".join(self.dp.output_buffer)


def read_binary(bin_path: str) -> tuple[list[int], list[int]]:
    with open(bin_path, "rb") as f:
        n_instr = struct.unpack(">I", f.read(4))[0]
        instructions = [struct.unpack(">I", f.read(4))[0] for _ in range(n_instr)]
        n_data = struct.unpack(">I", f.read(4))[0]
        raw_data = [struct.unpack(">I", f.read(4))[0] for _ in range(n_data)]
    data = []
    for w in raw_data:
        if w >= 0x80000000:
            w -= 0x100000000
        data.append(w)
    return instructions, data


def parse_input(input_path: str) -> list[tuple[int, str]]:
    schedule: list[tuple[int, str]] = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                tick = int(parts[0])
                raw = parts[1].strip()
                if raw.startswith("'") and raw.endswith("'"):
                    ch = raw[1:-1]
                    if ch == "\\n":
                        ch = "\n"
                    elif ch == "\\0":
                        ch = "\0"
                elif raw == "\\n":
                    ch = "\n"
                elif raw == "\\0":
                    ch = "\0"
                elif raw.lstrip("-").isdigit():
                    ch = chr(int(raw) & 0xFF)
                else:
                    ch = raw[0] if raw else "\0"
                schedule.append((tick, ch))
    return schedule


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: machine.py <program.bin> [input.txt] [log.txt]")
        sys.exit(1)

    bin_path = sys.argv[1]
    input_path: str | None = None
    log_path: str | None = None

    if len(sys.argv) == 3:
        arg = sys.argv[2]
        if arg.endswith(".log"):
            log_path = arg
        else:
            input_path = arg
    elif len(sys.argv) >= 4:
        input_path = sys.argv[2]
        log_path = sys.argv[3]

    instructions, data = read_binary(bin_path)
    schedule = parse_input(input_path) if input_path else []

    dp = DataPath(instructions, data)
    cu = ControlUnit(dp, schedule)

    if log_path:
        with open(log_path, "w") as log_file:
            cu.run(log_out=log_file)
    else:
        cu.run(log_out=None)

    print("".join(dp.output_buffer), end="")


if __name__ == "__main__":
    main()