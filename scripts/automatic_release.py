#!/usr/bin/env python3
"""Release an explicitly versioned commit after CI passes.

Adapted from bugsink/brotli-rs. Symalot's version is independent of its Rust
dependencies, so this script never edits package versions or makes commits.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from packaging.version import Version

from upstream_release_notes import release_notes


ROOT = Path(
    os.environ.get("AUTOMATIC_RELEASE_ROOT", Path(__file__).resolve().parent.parent)
).resolve()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def manifest(path: str, commit: str | None = None) -> dict:
    text = (ROOT / path).read_text() if commit is None else git("show", f"{commit}:{path}")
    return tomllib.loads(text)


def project_version(commit: str | None = None) -> str:
    python = manifest("pyproject.toml", commit)["project"]["version"]
    cargo = manifest("Cargo.toml", commit)["package"]["version"]
    if python != cargo:
        raise SystemExit("Cargo and Python package versions must match")
    return python


def dependency_version(dependency: str, commit: str | None = None) -> str:
    value = manifest("Cargo.toml", commit)["dependencies"][dependency]
    version = value if isinstance(value, str) else value["version"]
    if not version.startswith("="):
        raise SystemExit(f"{dependency} must have an exact version pin")
    return version[1:]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: automatic_release.py <previous-commit>")
    previous = sys.argv[1]
    old_version = project_version(previous)
    version = project_version()
    if version == old_version:
        print("No package version change; no release.")
        return 0
    if Version(version) <= Version(old_version):
        raise SystemExit("Release version must increase")
    if git("status", "--porcelain"):
        raise SystemExit("Release checkout must be clean")

    tag = f"v{version}"
    head = git("rev-parse", "HEAD")
    existing_tag = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if existing_tag.returncode == 0 and existing_tag.stdout.strip() != head:
        raise SystemExit(f"{tag} already points at a different commit")
    if existing_tag.returncode not in (0, 128):
        raise SystemExit(f"could not determine whether {tag} already exists")

    # Fetch provenance before creating a tag, so a failed lookup leaves no release behind.
    notes = [f"Release symalot {version}."]
    for dependency in ("symbolic-common", "minidump-processor"):
        old = dependency_version(dependency, previous)
        new = dependency_version(dependency)
        if old != new:
            notes.append(release_notes(dependency, new))

    if existing_tag.returncode == 128:
        subprocess.run(["git", "tag", tag], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "origin", tag], cwd=ROOT, check=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as notes_file:
        notes_file.write("\n\n".join(notes) + "\n")
        notes_file.flush()
        subprocess.run(
            ["gh", "release", "create", tag, "--verify-tag", "--notes-file", notes_file.name, "--title", tag],
            cwd=ROOT, check=True,
        )
    # Releases made with GITHUB_TOKEN don't trigger another workflow automatically.
    subprocess.run(
        ["gh", "workflow", "run", "release.yml", "--ref", "main", "-f", f"tag={tag}", "-f", "publish=true"],
        cwd=ROOT, check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
