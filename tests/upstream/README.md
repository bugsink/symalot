# Upstream tests

Each directory identifies its source project, pinned commit, original paths,
copyright, license, and adaptations in SOURCE.md. Binary fixtures are copied
byte-for-byte and have recorded hashes. Tests run without downloading fixtures.

* getsentry_symbolic/: selected symbolic Python tests and binary fixtures;
  Sentry and individual contributors, MIT. See getsentry_symbolic/SOURCE.md.

Symalot's own native API tests are in ../test_native.py. Their minidump data
has separate Google copyright and BSD terms in ../fixtures/LICENSE, with
provenance in ../fixtures/README.md. Release-tooling tests are in ../project/.
