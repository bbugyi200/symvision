"""Focused tests for external repository matching and fallback behavior."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import symvision.external as external
from symvision.external import (
    external_repo_references_symbol,
    is_external_repo_target,
    resolve_external_repo_roots,
)
from symvision.git import get_git_origin


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://github.com/Owner/Repo.git", "git:github.com/owner/repo"),
        ("ssh://git@github.com/Owner/Repo/", "git:github.com/owner/repo"),
        ("git@github.com:Owner/Repo.git", "git:github.com/owner/repo"),
        ("not-a-remote", None),
        ("", None),
    ],
)
def test_normalizes_supported_git_remote_forms(remote: str, expected: str | None) -> None:
    target = external._normalize_git_remote(remote)

    assert (target.normalized if target else None) == expected
    assert is_external_repo_target(remote) is (expected is not None)


def test_explicit_paths_precede_ordered_sibling_candidates(
    tmp_path: Path,
    make_repo: Callable[..., Path],
) -> None:
    remote = "https://github.com/example/consumer.git"
    producer = make_repo("producer", parent=tmp_path)
    explicit = make_repo("explicit", origin=remote, external=True)
    canonical = make_repo("consumer", parent=tmp_path, origin=remote, external=True)
    numbered = make_repo("consumer_2", parent=tmp_path, origin=remote, external=True)
    target = external._normalize_git_remote(remote)
    assert target is not None

    candidates = external._iter_external_repo_candidates(producer, [explicit], target)

    assert candidates[0] == explicit.resolve()
    assert candidates.index(canonical.resolve()) < candidates.index(numbered.resolve())


def test_resolves_file_uri_to_git_root(
    make_repo: Callable[..., Path],
) -> None:
    repo = make_repo()

    roots, error = resolve_external_repo_roots(f"file://{repo}", repo, [])

    assert roots == [repo]
    assert error is None


def test_rejects_unsupported_uri_and_repo_without_origin(
    tmp_path: Path,
    make_repo: Callable[..., Path],
) -> None:
    repo = make_repo()

    roots, error = resolve_external_repo_roots("not-a-uri", tmp_path, [])

    assert roots == []
    assert error == "unsupported external repository URI 'not-a-uri'"
    assert get_git_origin(repo) is None


def test_reuses_matching_cached_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_repo: Callable[..., Path],
) -> None:
    remote = "https://github.com/example/cache-consumer.git"
    producer = make_repo("producer", parent=tmp_path / "work")
    target = external._normalize_git_remote(remote)
    assert target is not None
    cache_dir = external._cache_dir_for_external_repo(target)
    subprocess.run(["git", "init", "-q", str(cache_dir)], check=True)
    subprocess.run(["git", "-C", str(cache_dir), "remote", "add", "origin", remote], check=True)
    monkeypatch.setattr(external, "_iter_external_repo_candidates", lambda *_args: [])

    roots, error = resolve_external_repo_roots(remote, producer, [])

    assert roots == [cache_dir]
    assert error is None


def test_reports_mismatched_existing_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_repo: Callable[..., Path],
) -> None:
    remote = "https://github.com/example/mismatch-consumer.git"
    producer = make_repo("producer", parent=tmp_path / "work")
    target = external._normalize_git_remote(remote)
    assert target is not None
    cache_dir = external._cache_dir_for_external_repo(target)
    cache_dir.mkdir(parents=True)
    monkeypatch.setattr(external, "_iter_external_repo_candidates", lambda *_args: [])

    roots, error = resolve_external_repo_roots(remote, producer, [])

    assert roots == []
    assert error is not None
    assert "cache path" in error


def test_reports_clone_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = "https://invalid.example/repo.git"
    monkeypatch.setattr(external, "_iter_external_repo_candidates", lambda *_args: [])
    monkeypatch.setattr(
        external, "_cache_dir_for_external_repo", lambda _target: tmp_path / "cache"
    )
    monkeypatch.setattr(external.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        external.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "clone failed"),
    )

    roots, error = resolve_external_repo_roots(remote, tmp_path, [])

    assert roots == []
    assert error == f"could not fetch external repository '{remote}': clone failed"


def test_non_python_tracked_file_can_reference_symbol(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
) -> None:
    repo = make_repo(origin="https://github.com/example/text.git", external=True)
    write_file(repo, "consumer/config.toml", 'factory = "WidgetFactory"\n')
    binary = repo / "consumer/binary.dat"
    binary.write_bytes(b"\xff\xfe")
    track_repo(repo)

    assert external_repo_references_symbol("WidgetFactory", repo, {"pkg.widgets"})
    assert not external_repo_references_symbol("MissingFactory", repo, {"pkg.widgets"})


def test_remote_matching_rejects_invalid_side() -> None:
    assert not external._normalizes_to_same_remote("invalid", "also-invalid")
    assert external._normalizes_to_same_remote(
        "git@github.com:Owner/Repo.git", "https://github.com/owner/repo"
    )
