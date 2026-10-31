import os
import re
import runpy
from pathlib import Path
import subprocess
import sys

import pytest


sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
RELEASE = runpy.run_path(Path(__file__).parents[2] / "scripts" / "automatic_release.py")


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
    git(root, "init", "--bare", "--quiet", "--initial-branch=main", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    write_versions(root, "0.1.0")
    (root / "Cargo.lock").write_text(
        'version = 4\n'
        '[[package]]\nname = "symbolic-common"\nversion = "13.9.0"\n'
        '[[package]]\nname = "minidump-processor"\nversion = "0.27.0"\n'
        '[[package]]\nname = "tokio"\nversion = "1.50.0"\n'
    )
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Initial version")
    return root


def run_release(root, previous):
    binary_dir = root.parent / "bin"
    binary_dir.mkdir(exist_ok=True)
    cargo = binary_dir / "cargo"
    cargo.write_text('#!/bin/sh\nprintf "%s\n" "$*" >> "$AUTOMATIC_RELEASE_ROOT/.git/cargo-calls"\nexit "${TEST_CARGO_EXIT:-0}"\n')
    cargo.chmod(0o755)
    gh = binary_dir / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$AUTOMATIC_RELEASE_ROOT/.git/gh-calls"\n')
    gh.chmod(0o755)
    env = dict(os.environ, AUTOMATIC_RELEASE_ROOT=str(root))
    env["PATH"] = str(binary_dir) + os.pathsep + env["PATH"]
    return subprocess.run(
        [sys.executable, "-c", (
            "import runpy, sys; "
            f"sys.path.insert(0, {str(SCRIPT.parent)!r}); "
            f"module = runpy.run_path({str(SCRIPT)!r}); "
            "module['main'].__globals__['release_notes'] = lambda crate, version: f'{crate} {version} provenance'; "
            f"sys.argv = [{str(SCRIPT)!r}, {previous!r}]; "
            "sys.exit(module['main']())"
        )], env=env, capture_output=True, text=True,
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


@pytest.mark.parametrize(("old", "new", "bump"), [
    ("13.9.0", "13.9.1", 1),
    ("13.9.1", "13.10.0", 2),
    ("13.10.0", "14.0.0", 3),
    ("0.27.0", "0.27.1", 1),
    ("0.27.0", "0.28.0", 3),
    ("0.27.0", "1.0.0", 3),
])
def test_upstream_release_boundaries(old, new, bump):
    assert RELEASE["upstream_bump"](old, new) == bump


@pytest.mark.parametrize(("old", "new"), [
    ("13.9.0", "13.8.0"), ("0.27.0", "0.28.0rc1"),
])
def test_upstream_downgrades_and_prereleases_require_review(old, new):
    with pytest.raises(SystemExit):
        RELEASE["upstream_bump"](old, new)


@pytest.mark.parametrize(("changes", "expected"), [
    ({"symbolic-common": "13.9.1"}, "1.2.4"),
    ({"symbolic-common": "13.10.0"}, "1.3.0"),
    ({"symbolic-common": "14.0.0"}, "2.0.0"),
    ({"minidump-processor": "0.28.0"}, "2.0.0"),
    ({"tokio": "2.0.0"}, "1.2.4"),
    ({"symbolic-common": "13.10.0", "minidump-processor": "0.28.0"}, "2.0.0"),
    ({"symbolic-common": "14.0.0", "symbolic-cfi": "14.0.0"}, "2.0.0"),
])
def test_dependency_update_releases_one_independent_version(repository, changes, expected):
    write_versions(repository, "1.2.3")
    lock = repository / "Cargo.lock"
    lock.write_text(lock.read_text() + '[[package]]\nname = "symbolic-cfi"\nversion = "13.9.0"\n')
    git(repository, "commit", "--quiet", "-am", "Start at 1.2.3")
    previous = git(repository, "rev-parse", "HEAD")
    text = lock.read_text()
    for name, version in changes.items():
        text = re.sub(r'(name = "' + name + r'"\nversion = ")[^"]+', r'\g<1>' + version, text)
    lock.write_text(text)
    git(repository, "commit", "--quiet", "-am", "Update dependencies")
    tested_commit = git(repository, "rev-parse", "HEAD")
    result = run_release(repository, previous)
    assert result.returncode == 0, result.stderr
    assert f'version = "{expected}"' in (repository / "Cargo.toml").read_text()
    assert f'version = "{expected}"' in (repository / "pyproject.toml").read_text()
    assert git(repository, "rev-parse", "HEAD^") == tested_commit
    assert git(repository, "rev-parse", f"v{expected}") == git(repository, "rev-parse", "HEAD")
    assert git(repository, "ls-remote", "origin", "refs/heads/main").split()[0] == git(repository, "rev-parse", "HEAD")
    assert (repository / ".git/cargo-calls").read_text() == "check\n"
    assert git(repository, "status", "--porcelain") == ""


def test_failed_version_build_does_not_push_tag_or_publish(repository, monkeypatch):
    previous = git(repository, "rev-parse", "HEAD")
    path = repository / "Cargo.lock"
    path.write_text(path.read_text().replace('"1.50.0"', '"1.50.1"'))
    git(repository, "commit", "--quiet", "-am", "Update tokio")
    tested_commit = git(repository, "rev-parse", "HEAD")
    monkeypatch.setenv("TEST_CARGO_EXIT", "1")
    result = run_release(repository, previous)
    assert result.returncode != 0
    assert git(repository, "tag") == ""
    assert git(repository, "rev-parse", "HEAD") == tested_commit
    assert git(repository, "ls-remote", "origin") == ""
    assert not (repository / ".git/gh-calls").exists()



def test_source_revision_update_without_version_change_releases_patch(repository):
    path = repository / "Cargo.lock"
    path.write_text(path.read_text().replace('name = "tokio"', 'source = "git+https://example.invalid/tokio#abc"\nname = "tokio"'))
    git(repository, "commit", "--quiet", "-am", "Pin a source revision")
    previous = git(repository, "rev-parse", "HEAD")
    path.write_text(path.read_text().replace("tokio#abc", "tokio#def"))
    git(repository, "commit", "--quiet", "-am", "Update the source revision")
    result = run_release(repository, previous)
    assert result.returncode == 0, result.stderr
    assert git(repository, "tag") == "v0.1.1"


def test_explicit_patch_cannot_hide_a_core_major_update(repository):
    previous = git(repository, "rev-parse", "HEAD")
    path = repository / "Cargo.lock"
    path.write_text(path.read_text().replace('"0.27.0"', '"0.28.0"'))
    write_versions(repository, "0.1.1")
    git(repository, "commit", "--quiet", "-am", "Understate a breaking update")
    result = run_release(repository, previous)
    assert result.returncode != 0
    assert "require at least symalot 1.0.0" in result.stderr
    assert git(repository, "tag") == ""
    assert not (repository / ".git/gh-calls").exists()


def test_concurrent_main_update_is_not_overwritten_or_released(repository):
    previous = git(repository, "rev-parse", "HEAD")
    git(repository, "push", "--quiet", "origin", "HEAD:main")
    other = repository.parent / "other"
    git(repository, "clone", "--quiet", str(repository.parent / "remote.git"), str(other))
    git(other, "config", "user.name", "Concurrent update")
    git(other, "config", "user.email", "other@example.invalid")
    git(other, "config", "commit.gpgsign", "false")
    git(other, "commit", "--quiet", "--allow-empty", "-m", "Another update")
    git(other, "push", "--quiet", "origin", "HEAD:main")
    remote_commit = git(other, "rev-parse", "HEAD")
    path = repository / "Cargo.lock"
    path.write_text(path.read_text().replace('"1.50.0"', '"1.50.1"'))
    git(repository, "commit", "--quiet", "-am", "Update tokio")
    result = run_release(repository, previous)
    assert result.returncode != 0
    assert git(repository, "ls-remote", "origin", "refs/heads/main").split()[0] == remote_commit
    assert git(repository, "tag") == ""
    assert not (repository / ".git/gh-calls").exists()



def test_core_upgrade_counts_when_cargo_keeps_the_old_version_too(repository):
    write_versions(repository, "1.2.3")
    git(repository, "commit", "--quiet", "-am", "Start at 1.2.3")
    previous = git(repository, "rev-parse", "HEAD")
    path = repository / "Cargo.lock"
    path.write_text(path.read_text() + '[[package]]\nname = "symbolic-common"\nversion = "14.0.0"\n')
    git(repository, "commit", "--quiet", "-am", "Upgrade symbolic, retaining an older copy")
    result = run_release(repository, previous)
    assert result.returncode == 0, result.stderr
    assert git(repository, "tag") == "v2.0.0"



def test_release_includes_core_update_before_the_latest_ci_parent(repository):
    write_versions(repository, "1.2.3")
    git(repository, "commit", "--quiet", "-am", "Start at 1.2.3")
    git(repository, "tag", "v1.2.3")
    path = repository / "Cargo.lock"
    path.write_text(path.read_text().replace('"13.9.0"', '"14.0.0"'))
    manifest = repository / "Cargo.toml"
    manifest.write_text(manifest.read_text().replace('"=13.9.0"', '"=14.0.0"'))
    git(repository, "commit", "--quiet", "-am", "Upgrade symbolic before the next CI parent")
    previous = git(repository, "rev-parse", "HEAD")
    git(repository, "commit", "--quiet", "--allow-empty", "-m", "Another change lands while CI runs")
    result = run_release(repository, previous)
    assert result.returncode == 0, result.stderr
    assert 'version = "2.0.0"' in manifest.read_text()
    assert git(repository, "tag", "--list", "v2.0.0") == "v2.0.0"
