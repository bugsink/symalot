# Vendored symbolic tests

Vendored from [getsentry/symbolic 13.9.0](https://github.com/getsentry/symbolic/tree/a823d6f3f5197f5b1fe6c74c0ec126ec030a0a3a),
commit `a823d6f3f5197f5b1fe6c74c0ec126ec030a0a3a`.
Copyright (c) 2017 Sentry (https://sentry.io) and individual contributors.
Local adaptations: Copyright (c) 2026 Bugsink.
The upstream MIT license is copied unchanged to LICENSE.

These are selected upstream Python tests adapted to symalot's smaller API,
not a copy of the whole upstream suite:

| Local file | Original file and selected tests | Adaptation |
| --- | --- | --- |
| test_cfi.py | [py/tests/test_cfi.py](https://github.com/getsentry/symbolic/blob/a823d6f3f5197f5b1fe6c74c0ec126ec030a0a3a/py/tests/test_cfi.py), both tests | Replace Archive/Object/cache streams with generate_cfi(bytes). Keep the byte-for-byte expected CFI assertions. |
| test_symcache.py | [py/tests/test_symcache.py](https://github.com/getsentry/symbolic/blob/a823d6f3f5197f5b1fe6c74c0ec126ec030a0a3a/py/tests/test_symcache.py), test_symbolicate_electron_darwin_dsym and test_symbolicate_electron_darwin_sym | Replace Archive/Object/SymCache with lookup_addresses. Rename symbol/full_path to function_name/filename. Keep the original address, function, line and path expectations. Omit cache serialization and language assertions: symalot exposes neither. |
| test_debug.py | [py/tests/test_debug.py](https://github.com/getsentry/symbolic/blob/a823d6f3f5197f5b1fe6c74c0ec126ec030a0a3a/py/tests/test_debug.py), test_id_from_breakpad and test_normalize_debug_id | Both use symalot.normalize_debug_id. Omit None passthrough assertions: symalot requires a string. All string inputs and expected IDs are unchanged. |

Every file below res/ is copied **without modification** from the same path
below upstream py/tests/res/ at that commit. This includes executable-format
fixtures and their expected .sym output; tests parse these binaries, never
execute them. SHA256SUMS records their hashes. The original fixture directory
structure is preserved.

The tests in ../../test_native.py were written for symalot, rather than
vendored from symbolic. Their minidump fixtures have separate provenance in
../../fixtures/README.md. Tests in ../../project/ cover release tooling;
that tooling and its release-note tests were adapted from brotli_rs.

When updating these vendored files, record the new upstream commit and any
additional adaptations here. Do not regenerate expected output silently.
