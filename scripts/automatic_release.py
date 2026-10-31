#!/usr/bin/env python3
"""Prepare an independently versioned symalot release after green CI.

Adapted from bugsink/brotli-rs. Dependency updates choose a version bump;
the release workflow builds and tests the versioned artifacts before publishing.
"""

from __future__ import annotations

import os
import re
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


def locked_packages(commit: str | None = None) -> list[dict]:
    return [package for package in manifest("Cargo.lock", commit)["package"] if package["name"] != "symalot"]


def locked_dependencies(commit: str | None = None) -> dict[str, set[str]]:
    packages = {}
    for package in locked_packages(commit):
        packages.setdefault(package["name"], set()).add(package["version"])
    return packages


def upstream_bump(old: str, new: str) -> int:
    """Return patch=1, minor=2 or major=3 for a core upstream update."""
    before, after = Version(old), Version(new)
    if before.is_prerelease or after.is_prerelease or before.is_devrelease or after.is_devrelease:
        raise SystemExit("Prerelease upstream updates need an explicit release decision")
    if after <= before:
        raise SystemExit(f"Upstream version must increase: {old} -> {new}")
    if after.major != before.major or (before.major == 0 and after.minor != before.minor):
        return 3
    if after.minor != before.minor:
        return 2
    return 1


def dependency_release_version(previous: str, current: str) -> str | None:
    old, new = locked_dependencies(previous), locked_dependencies()
    if (
        locked_packages(previous) == locked_packages()
        and manifest("Cargo.toml", previous)["dependencies"] == manifest("Cargo.toml")["dependencies"]
    ):
        return None
    bump = 1
    for name in old.keys() & new.keys():
        if old[name] == new[name]:
            continue
        if name.startswith("symbolic-") or name == "minidump" or name.startswith("minidump-"):
            removed, added = old[name] - new[name], new[name] - old[name]
            if added:
                before = max(removed or old[name], key=Version)
                after = max(added, key=Version)
                # Cargo can retain an older copy for another dependency.
                if removed or Version(after) > Version(before):
                    bump = max(bump, upstream_bump(before, after))
    version = Version(current)
    if version.is_prerelease or len(version.release) != 3 or str(version) != current:
        raise SystemExit("Symalot automatic releases require an X.Y.Z version")
    major, minor, patch = version.release
    if bump == 3:
        return f"{major + 1}.0.0"
    if bump == 2:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_project_version(version: str) -> None:
    for filename in ("Cargo.toml", "pyproject.toml"):
        path = ROOT / filename
        text, count = re.subn(
            r'(?m)^version\s*=\s*"[^"\n]+"$', f'version = "{version}"', path.read_text(), count=1,
        )
        if count != 1:
            raise SystemExit(f"Could not update package version in {filename}")
        path.write_text(text)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: automatic_release.py <previous-commit>")
    previous = sys.argv[1]
    old_version = project_version(previous)
    version = project_version()
    automatic = version == old_version
    expected = dependency_release_version(previous, old_version)
    if automatic:
        if expected is None:
            print("No Rust dependency or package version change; no release.")
            return 0
        version = expected
    elif Version(version) <= Version(old_version):
        raise SystemExit("Release version must increase")
    elif expected is not None and Version(version) < Version(expected):
        raise SystemExit(f"Dependency changes require at least symalot {expected}")
    if git("status", "--porcelain"):
        raise SystemExit("Release checkout must be clean")

    tag = f"v{version}"
    head = git("rev-parse", "HEAD")
    existing_tag = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if existing_tag.returncode == 0 and (automatic or existing_tag.stdout.strip() != head):
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

    old_dependencies, new_dependencies = locked_dependencies(previous), locked_dependencies()
    tested_packages = locked_packages()
    for name in sorted(old_dependencies.keys() | new_dependencies.keys()):
        old = ", ".join(sorted(old_dependencies.get(name, set()))) or "absent"
        new = ", ".join(sorted(new_dependencies.get(name, set()))) or "absent"
        if old != new:
            notes.append(f"- {name}: {old} -> {new}")

    if automatic:
        write_project_version(version)
        subprocess.run(["cargo", "check"], cwd=ROOT, check=True)
        if locked_packages() != tested_packages:
            raise SystemExit("Preparing the release changed dependencies; run CI again")
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
        subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
        subprocess.run(["git", "add", "Cargo.toml", "Cargo.lock", "pyproject.toml"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"Release symalot {version}"], cwd=ROOT, check=True)
        # A normal push refuses to overwrite main if another update landed meanwhile.
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=ROOT, check=True)

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
