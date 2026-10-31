import gc
from pathlib import Path

import pytest
import symalot


FIXTURES = Path(__file__).parent / "fixtures"
DEBUG_ID = "7B7D1968FF0D47AE4366E9C3A7E1B6750"
SYMBOLS = b"""MODULE Linux x86_64 7B7D1968FF0D47AE4366E9C3A7E1B6750 null_read_av
FILE 0 src/main.c
FUNC 2170 8 0 crash
2170 8 6 0
STACK CFI INIT 2170 8 .cfa: $rsp 8 + .ra: .cfa -8 + ^
"""


def test_linux_results_survive_input_and_parent_objects():
    data = (FIXTURES / "linux_null_read_av.dmp").read_bytes()
    state = symalot.process_minidump(data)
    assert state.crashed
    assert state.crash_reason == "SIGSEGV"
    assert state.requesting_thread == 0
    assert state.system_info.os_name == "Linux"
    assert state.system_info.cpu == "amd64"
    frame = state.threads[0].frames[0]
    module = next(module for module in state.modules if module.addr <= frame.instruction < module.addr + module.size)
    del data, state
    gc.collect()
    assert frame.instruction == 0x402170
    assert frame.trust == "context"
    assert module.debug_id == symalot.normalize_debug_id(DEBUG_ID)
    assert module.code_file.endswith("/null_read_av")


def test_windows_dump():
    state = symalot.process_minidump((FIXTURES / "ascii_read_av.dmp").read_bytes())
    assert state.crash_reason == "EXCEPTION_ACCESS_VIOLATION_READ"
    assert state.system_info.cpu == "x86"
    assert len(state.threads) == 2
    frames = state.threads[state.requesting_thread].frames
    assert frames[0].instruction == 0xD6A6CD
    assert frames[1].trust == "frame_pointer"


@pytest.mark.parametrize("cfi_type", [bytes, bytearray])
def test_generated_cfi_recovers_the_caller(cfi_type):
    data = (FIXTURES / "linux_null_read_av.dmp").read_bytes()
    without_cfi = symalot.process_minidump(data)
    cfi = symalot.generate_cfi(SYMBOLS)
    with_cfi = symalot.process_minidump(data, {DEBUG_ID: cfi_type(cfi)})
    assert without_cfi.threads[0].frames[1].trust == "scan"
    frames = with_cfi.threads[0].frames
    assert frames[0].instruction == 0x402170
    assert frames[1].instruction == 0x401FCE
    assert frames[1].trust == "cfi"


def test_debug_file_without_unwind_information():
    cfi = symalot.generate_cfi(SYMBOLS.split(b"STACK CFI")[0])
    assert cfi == b""
    state = symalot.process_minidump(
        (FIXTURES / "linux_null_read_av.dmp").read_bytes(), {DEBUG_ID: cfi}
    )
    assert state.crash_reason == "SIGSEGV"
    assert state.threads[0].frames[1].trust == "scan"


def test_batch_lookup_returns_owned_locations_and_preserves_order():
    data = bytes(bytearray(SYMBOLS))
    assert symalot.debug_file_kind(data) == "dbg"
    results = symalot.lookup_addresses(data, [0x2170, 0x9999, 0x2171])
    first = results[0][0]
    del data, results
    gc.collect()
    assert (first.function_name, first.filename, first.line) == ("crash", "src/main.c", 6)
    results = symalot.lookup_addresses(SYMBOLS, [0x2170, 0x9999, 0x2171])
    assert results[1] == []
    assert results[2][0].function_name == "crash"


def test_cpp_function_names_are_demangled():
    symbols = SYMBOLS.replace(b"0 crash\n", b"0 _ZN3foo3barEv\n")
    assert symalot.lookup_addresses(symbols, [0x2170])[0][0].function_name == "foo::bar()"


def test_debug_id_preserves_the_pdb_age():
    assert symalot.normalize_debug_id("1B5043085F174DA385521DD4740D173014") == (
        "1b504308-5f17-4da3-8552-1dd4740d1730-14"
    )


@pytest.mark.parametrize("parse", [symalot.debug_file_kind, symalot.generate_cfi, lambda data: symalot.lookup_addresses(data, [0])])
def test_source_bundles_are_rejected_before_manifest_parsing(parse):
    with pytest.raises(ValueError, match="Expected debug information, got a source bundle"):
        parse(b"SYSB\x02\x00\x00\x00")


@pytest.mark.parametrize("parse", [symalot.process_minidump, symalot.debug_file_kind, symalot.generate_cfi])
def test_invalid_input_is_a_python_error(parse):
    with pytest.raises(ValueError):
        parse(b"not a binary file")
