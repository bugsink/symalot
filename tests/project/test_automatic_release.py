import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "automatic_release.py"


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def write_versions(root, python_version, cargo_version=None):
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{python_version}"\n')
    (root / "Cargo.toml").write_text(
        f'[package]\nversion = "{cargo_version or python_version}"\n'
        '[dependencies]\nsymbolic-common = "=13.9.0"\n'
        'minidump-processor = { version = "=0.27.0", default-features = false }\n'
    )


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    git(root, "config", "user.name", "Release test")
    git(root, "config", "user.email", "release@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "tag.gpgsign", "false")
    remote = tmp_path / "remote.git"
    git(root, "init", "--bare", "--quiet", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    write_versions(root, "0.1.0")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Initial version")
    return root


def run_release(root, previous):
    binary_dir = root.parent / "bin"
    binary_dir.mkdir()
    gh = binary_dir / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$AUTOMATIC_RELEASE_ROOT/.git/gh-calls"\n')
    gh.chmod(0o755)
    env = dict(os.environ, AUTOMATIC_RELEASE_ROOT=str(root))
    env["PATH"] = str(binary_dir) + os.pathsep + env["PATH"]
    return subprocess.run(
        [sys.executable, str(SCRIPT), previous], env=env, capture_output=True, text=True,
    )


def test_unchanged_package_version_does_not_release(repository):
    previous = git(repository, "rev-parse", "HEAD")
    git(repository, "commit", "--quiet", "--allow-empty", "-m", "Documentation")
    result = run_release(repository, previous)
    assert result.returncode == 0, result.stderr
    assert git(repository, "tag") == ""
    assert not (repository / ".git/gh-calls").exists()


def test_release_tags_the_versioned_commit_without_changing_it(repository):
    previous = git(repository, "rev-parse", "HEAD")
    write_versions(repository, "0.1.1")
    git(repository, "commit", "--quiet", "-am", "Release 0.1.1")
    tested_commit = git(repository, "rev-parse", "HEAD")
    result = run_release(repository, previous)
    assert result.returncode == 0, result.stderr
    assert git(repository, "rev-parse", "HEAD") == tested_commit
    assert git(repository, "rev-parse", "v0.1.1") == tested_commit
    assert git(repository, "ls-remote", "origin", "refs/tags/v0.1.1").split()[0] == tested_commit
    assert git(repository, "status", "--porcelain") == ""
    calls = (repository / ".git/gh-calls").read_text().splitlines()
    assert calls[0].startswith("release create v0.1.1 --verify-tag --notes-file ")
    assert calls[1] == "workflow run release.yml --ref main -f tag=v0.1.1 -f publish=true"


def test_release_refuses_a_tag_pointing_to_another_commit(repository):
    previous = git(repository, "rev-parse", "HEAD")
    git(repository, "tag", "v0.1.1")
    write_versions(repository, "0.1.1")
    git(repository, "commit", "--quiet", "-am", "Release 0.1.1")
    result = run_release(repository, previous)
    assert result.returncode != 0
    assert "already points at a different commit" in result.stderr
    assert git(repository, "rev-parse", "v0.1.1") == previous
    assert not (repository / ".git/gh-calls").exists()


def test_release_refuses_disagreeing_package_versions(repository):
    previous = git(repository, "rev-parse", "HEAD")
    write_versions(repository, "0.1.1", "0.2.0")
    git(repository, "commit", "--quiet", "-am", "Mismatched versions")
    result = run_release(repository, previous)
    assert result.returncode != 0
    assert "versions must match" in result.stderr
    assert git(repository, "tag") == ""
    assert not (repository / ".git/gh-calls").exists()
