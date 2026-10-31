# Copyright (c) 2017 Sentry (https://sentry.io) and individual contributors.
# Copyright (c) 2026 Bugsink.
# MIT license; see LICENSE in this directory.
# Adapted from getsentry/symbolic; see SOURCE.md for the pinned source and changes.
from pathlib import Path

import symalot


RES = Path(__file__).parent / "res" / "electron/1.8.1/Electron/CB63147AC9DC308B8CA1EE92A5042E8E0"


def test_symbolicate_electron_darwin_dsym():
    data = (RES / "Electron.app.dSYM/Contents/Resources/DWARF/Electron").read_bytes()
    symbol = symalot.lookup_addresses(data, [0x107BB9F25 - 0x107BB9000])[0][0]
    assert symbol.function_name == "main"
    assert symbol.line == 186
    assert symbol.filename == "/Users/electron/workspace/electron-osx-x64/atom/app/atom_main.cc"


def test_symbolicate_electron_darwin_sym():
    data = (RES / "Electron.sym").read_bytes()
    symbol = symalot.lookup_addresses(data, [0x107BB9F25 - 0x107BB9000])[0][0]
    assert symbol.function_name == "main"
    assert symbol.line == 186
    assert symbol.filename == "/Users/electron/workspace/electron-osx-x64/atom/app/atom_main.cc"
