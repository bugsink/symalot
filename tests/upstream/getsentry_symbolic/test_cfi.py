# Copyright (c) 2017 Sentry (https://sentry.io) and individual contributors.
# Copyright (c) 2026 Bugsink.
# MIT license; see LICENSE in this directory.
# Adapted from getsentry/symbolic; see SOURCE.md for the pinned source and changes.
from pathlib import Path

import symalot


RES = Path(__file__).parent / "res" / "minidump"


def test_macos_cficache():
    assert symalot.generate_cfi((RES / "crash_macos").read_bytes()) == (RES / "crash_macos.sym").read_bytes()


def test_linux_cficache():
    assert symalot.generate_cfi((RES / "crash_linux").read_bytes()) == (RES / "crash_linux.sym").read_bytes()
