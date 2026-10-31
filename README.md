# Symalot

Small Python bindings for the Rust libraries used to process native crash reports
and debug files. The initial interface serves Bugsink's minidump handling.

This is a proof of concept, not a compatible replacement for `import symbolic`.
Use `import symalot`. Symbolic is a Rust dependency, not a source fork.

The binding crate forbids handwritten unsafe Rust. Returned results own their data;
they do not borrow from a parser or Python input buffer. Upstream dependencies may
use unsafe code internally. Swift's C++ demangler is disabled; Breakpad's C++
processor is not used.

For local development, with Rust and a project virtual environment installed:

```
python -m pip install maturin pytest
python -m pip install -e .
python -m pytest
```

Rebuild after changing Rust code. `Cargo.lock` records the dependency versions used
by CI. Native builds cover Linux and macOS on x86_64 and ARM64.

## Initial API

* `debug_file_kind(data)` identifies exactly one debug object; returns e.g. `"dbg"`.
* `generate_cfi(data)` returns ASCII unwind information as Python bytes.
* `lookup_addresses(data, addresses)` parses once and returns one list of source
  locations per module-relative address, preserving input order and inline frames.
  Locations have `function_name`, `filename` (full path), and `line` attributes.
* `normalize_debug_id(value)` returns a canonical debug ID, preserving PDB age.
* `process_minidump(data, cfi=None)` returns crash metadata, system information,
  loaded modules, and threads with instruction addresses and frame trust.
  `cfi` maps debug IDs to ASCII unwind bytes. Processing uses only these inputs,
  with no filesystem or network symbol lookup.

Results expose attributes, including `state.threads[0].frames[0].instruction`.
`requesting_thread` is an index or `None`. Missing strings may be `None`.
Child results remain usable after discarding the input and parent results.
Source bundles are rejected before parsing in all debug-file operations.

Versions are independent of upstream symbolic. The initial dependencies are
symbolic 13.9.0 and rust-minidump 0.27.0. No package has been published yet;
use an editable install for the Bugsink integration branch.

## Releases

Release workflows, scripts, and release-note tests are adapted from
[bugsink/brotli-rs at 1ffbb62de6bcc3722ebd55423a518a90c8a9be92](https://github.com/bugsink/brotli-rs/tree/1ffbb62de6bcc3722ebd55423a518a90c8a9be92):
`.github/workflows/release.yml`, `.github/workflows/automatic-release.yml`,
`scripts/automatic_release.py`, `scripts/upstream_release_notes.py`, and
`tests/project/test_upstream_release_notes.py`. The automatic-release tests
were written for symalot. Unlike brotli-rs, symalot requires an explicit package
version bump; dependency updates do not choose a version or create a commit.

The manual `Release` workflow can
build a commit or branch with `publish=false` (the default), test the four wheels
and a build from the sdist, and save the distributions as workflow artifacts.
Linux wheels target glibc 2.28 or newer. Windows and musllinux are excluded.

Publication requires a `vVERSION` tag matching both package manifests. A published
GitHub release or a manual run with `publish=true` uploads the tested artifacts
through PyPI Trusted Publishing, using the GitHub environment `pypi`.

Automatic releases are disabled unless the repository variable
`AUTOMATIC_RELEASES` is set to `true`. Once enabled, green CI on a commit that
explicitly increases both package versions triggers tagging and publishing.
Dependency updates alone do not select a package version. The release script
does not edit versions or create commits. Upstream notes use the published crate's
source commit where recorded. Symbolic omits that metadata, so its attribution
explicitly identifies the upstream release tag instead.

The first release, versioning policy, and PyPI configuration still need review.

## License and upstream material

Symalot's implementation is new code, copyright 2026 Bugsink, under the MIT
license in [LICENSE](LICENSE). This repository is not a source fork of symbolic.

Adapted symbolic tests and copied fixtures live in
[tests/upstream/getsentry_symbolic](tests/upstream/getsentry_symbolic/SOURCE.md),
with Sentry's copyright and upstream MIT license kept there. The minidump
fixtures in [tests/fixtures](tests/fixtures/README.md) carry Google's copyright
and their own BSD license. These notices apply to that material; they do not
attribute symalot's implementation to Sentry or Google.

Rust dependencies retain their own copyrights and licenses.
