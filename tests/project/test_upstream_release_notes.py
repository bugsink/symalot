import io
import json
import runpy
import tarfile
from pathlib import Path

import pytest


SCRIPT = runpy.run_path(
    Path(__file__).parents[2] / "scripts" / "upstream_release_notes.py"
)
format_release_notes = SCRIPT["format_release_notes"]
source_commit_from_archive = SCRIPT["source_commit_from_archive"]


def crate_archive(crate, version, vcs_info):
    contents = json.dumps(vcs_info).encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        if vcs_info is not None:
            member = tarfile.TarInfo(f"{crate}-{version}/.cargo_vcs_info.json")
            member.size = len(contents)
            archive.addfile(member, io.BytesIO(contents))
    return output.getvalue()


def test_source_commit_comes_from_published_crate_metadata():
    commit = "0123456789abcdef0123456789abcdef01234567"
    archive = crate_archive("symbolic-common", "13.9.0", {"git": {"sha1": commit}})

    assert source_commit_from_archive(archive, "symbolic-common", "13.9.0") == commit


def test_source_commit_requires_cargo_vcs_metadata():
    archive = crate_archive("symbolic-common", "13.9.0", {})

    with pytest.raises(RuntimeError, match="no valid source commit"):
        source_commit_from_archive(archive, "symbolic-common", "13.9.0")


def test_symbolic_without_vcs_metadata_is_attributed_to_its_release_tag(monkeypatch):
    release_notes = SCRIPT["release_notes"]
    monkeypatch.setitem(
        release_notes.__globals__, "download_crate",
        lambda crate, version: crate_archive(crate, version, None),
    )
    notes = release_notes("symbolic-common", "13.9.0")
    assert "https://github.com/getsentry/symbolic/tree/13.9.0" in notes
    assert "published crate has no source commit metadata" in notes
    assert "Upstream source commit" not in notes


def test_release_notes_preserve_upstream_message_and_add_attribution():
    commit = "0123456789abcdef0123456789abcdef01234567"

    notes = format_release_notes(
        "symbolic-common",
        "13.9.0",
        "getsentry/symbolic",
        commit,
        "Fix symbol lookup\n\n* Keep this upstream detail",
        "Update to symbolic 13.9.0",
    )

    assert notes == (
        "## Upstream symbolic-common 13.9.0 release notes\n\n"
        "Fix symbol lookup\n\n"
        "* Keep this upstream detail\n\n"
        "[Upstream source commit 0123456789ab]"
        "(https://github.com/getsentry/symbolic/commit/"
        "0123456789abcdef0123456789abcdef01234567)\n\n"
        "## symalot notes\n\n"
        "Update to symbolic 13.9.0\n"
    )
