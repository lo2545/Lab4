import subprocess
import sys

PYTHON = sys.executable


def translate_and_run(forth_file: str, input_file: str | None = None) -> str:
    bin_file = forth_file.replace(".forth", ".bin").replace("programs/", "out/")
    result = subprocess.run(
        [PYTHON, "translator.py", forth_file, bin_file],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"translator failed: {result.stderr}"

    args = [PYTHON, "machine.py", bin_file]
    if input_file:
        args.append(input_file)
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, f"machine failed: {result.stderr}"
    return result.stdout


def test_hello() -> None:
    output = translate_and_run("programs/hello.forth")
    assert output == "Hello, World!"


def test_harvard_memory() -> None:
    dbg = open("golden_tests/hello/hello.dbg").read()
    assert "=== INSTRUCTION MEMORY ===" in dbg
    assert "=== DATA MEMORY ===" in dbg
    instr_lines = [l for l in dbg.splitlines() if l and not l.startswith("=") and "INSTRUCTION" not in l and "DATA" not in l and dbg.find("DATA") > dbg.find(l)]
    assert len(instr_lines) > 0


def test_cat() -> None:
    output = translate_and_run("programs/cat.forth", "golden_tests/cat/input.txt")
    assert output == "hello"


def test_hello_user_name() -> None:
    output = translate_and_run(
        "programs/hello_user_name.forth",
        "golden_tests/hello_user_name/input.txt",
    )
    assert "What is your name?" in output
    assert "Hello, Alice!" in output


def test_sort() -> None:
    output = translate_and_run("programs/sort.forth", "golden_tests/sort/input.txt")
    values = [ord(c) for c in output]
    assert values == sorted(values), f"not sorted: {values}"
    assert sorted(values) == [12, 21, 45, 53, 64]


def test_prob2() -> None:
    output = translate_and_run("programs/prob2.forth", "golden_tests/prob2/input.txt")
    assert output.strip() == "4613732"


def test_double_precision() -> None:
    output = translate_and_run("programs/double_precision.forth")
    parts = output.strip().split()
    assert len(parts) == 2
    hi, lo = int(parts[0]), int(parts[1])
    result = (hi << 32) | (lo & 0xFFFFFFFF)
    expected = 1000000000 + 1500000000
    assert result & 0xFFFFFFFF == expected & 0xFFFFFFFF


def test_vector_demo() -> None:
    output = translate_and_run("programs/vector_demo.forth")
    lines = output.strip().splitlines()
    assert len(lines) == 2
    scalar_results = list(map(int, lines[0].split()))
    vector_results = list(map(int, lines[1].split()))
    assert scalar_results == [60, 80, 100, 120]
    assert vector_results == [60, 80, 100, 120]
