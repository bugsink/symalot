# Symalot

<img src="https://raw.githubusercontent.com/bugsink/symalot/main/symalot-logo.png" width="480" alt="Symalot logo">

Small Python bindings for the Rust libraries used to process native crash reports
and debug files. The initial interface serves Bugsink's minidump handling.

## Initial API

* `debug_file_kind(data)` identifies exactly one debug object; returns e.g. `"dbg"`.
* `generate_cfi(data)` returns ASCII unwind information as Python bytes.
* `lookup_addresses(data, addresses)` parses once and returns one list of source
  locations per module-relative address, preserving input order and inline frames.
  Locations have `function_name`, `filename` (full path), and `line` attributes.
* `normalize_debug_id(value)` returns a canonical debug ID, preserving PDB age.
* `minidump_modules(data)` returns loaded modules without unwinding threads;
  use it to find the CFI files needed before processing a dump.
* `process_minidump(data, cfi=None)` returns crash metadata, system information,
  loaded modules, and threads with instruction addresses and frame trust.
  `cfi` maps debug IDs to ASCII unwind bytes. Processing uses only these inputs,
  with no filesystem or network symbol lookup.

## License and upstream material

Copyright 2026 Bugsink, under the MIT license in [LICENSE](LICENSE).

Adapted symbolic tests and copied fixtures live in
[tests/upstream/getsentry_symbolic](tests/upstream/getsentry_symbolic/SOURCE.md),
with Sentry's copyright and upstream MIT license kept there. The minidump
fixtures in [tests/fixtures](tests/fixtures/README.md) carry Google's copyright
and their own BSD license. 

Rust dependencies retain their own copyrights and licenses.
