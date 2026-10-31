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
* `minidump_modules(data)` returns loaded modules without unwinding threads;
  use it to find the CFI files needed before processing a dump.
* `process_minidump(data, cfi=None)` returns crash metadata, system information,
  loaded modules, and threads with instruction addresses and frame trust.
  `cfi` maps debug IDs to ASCII unwind bytes. Processing uses only these inputs,
  with no filesystem or network symbol lookup.

Results expose attributes, including `state.threads[0].frames[0].instruction`.
`requesting_thread` is an index or `None`. Missing strings may be `None`.
Child results remain usable after discarding the input and parent results.
Modules, threads and frames are immutable tuples of objects created once;
reading an attribute again does not clone the result tree.
Source bundles are rejected before parsing in all debug-file operations.

Versions are independent of upstream symbolic. The initial dependencies are
symbolic 13.9.0 and rust-minidump 0.27.0. No package has been published yet;
use an editable install for the Bugsink integration branch.

## Releases

Release workflows, scripts, and release-note tests are adapted from
[bugsink/brotli-rs at 1ffbb62de6bcc3722ebd55423a518a90c8a9be92](https://github.com/bugsink/brotli-rs/tree/1ffbb62de6bcc3722ebd55423a518a90c8a9be92):
`.github/dependabot.yml`, `.github/workflows/dependabot-automerge.yml`,
`.github/workflows/release.yml`, `.github/workflows/automatic-release.yml`,
`scripts/automatic_release.py`, `scripts/upstream_release_notes.py`, and
`tests/project/test_upstream_release_notes.py`. The automatic-release tests
were written for symalot. Symalot uses independent release numbers rather than
matching a single upstream's version.

Dependabot checks Rust dependencies daily, grouping symbolic and rust-minidump
separately from supporting crates. Supporting crates have a three-day cooldown;
Python tooling and GitHub Actions are checked weekly. Green Dependabot PRs are
squash-merged only after verifying that CI tested the current PR commit, then CI
is dispatched on main because merges using GITHUB_TOKEN do not trigger push CI.

The manual `Release` workflow can
build a commit or branch with `publish=false` (the default), test the four wheels
and a build from the sdist, and save the distributions as workflow artifacts.
Linux wheels target glibc 2.28 or newer. Windows and musllinux are excluded.

Publication requires a `vVERSION` tag matching both package manifests. A published
GitHub release or a manual run with `publish=true` uploads the tested artifacts
through PyPI Trusted Publishing, using the GitHub environment `pypi`.

Automatic releases are disabled unless the repository variable
`AUTOMATIC_RELEASES` is set to `true`. Once enabled, green CI on main selects
one version bump for a Rust dependency update, starting from symalot 1.0.0:

* Symbolic and rust-minidump major/minor/patch updates produce the corresponding
  symalot bump. For upstream 0.x, a minor update produces a symalot major bump.
* The largest bump wins across all updated crates; a group produces one release.
* Supporting Rust dependency updates, including transitive updates, produce a
  patch release. Tooling-only changes produce no release.
* Our own changes use an explicit version bump in Cargo.toml and pyproject.toml.
  An explicit bump accompanying dependency updates must meet their minimum bump.

As in brotli-rs, the script prepares a version commit and updates Cargo.lock with
cargo check, then pushes and tags it. Dependency resolution must stay unchanged.
The release workflow builds and tests the final versioned wheels and sdist before
publishing. Automatic merges dispatch main CI explicitly, and that CI can trigger
the release check too. Prerelease upstream versions and core downgrades require
manual handling.

Upstream notes list changed crate versions and use the published crate's source
commit where recorded. Symbolic omits that metadata, so its attribution explicitly
identifies the upstream release tag instead.

The first release and PyPI configuration still need review.

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
