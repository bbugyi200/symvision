"""External-repository pragma resolution and validation."""

import hashlib
import os
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from symvision.discovery import find_git_tracked_files, is_test_support_file_path
from symvision.git import get_git_origin, get_git_root
from symvision.models import ExternalRepoTarget, FileInfo
from symvision.scanner import batch_search_usage, extract_file_info


def is_external_repo_target(ref_path: str) -> bool:
    """Return whether a pragma target is an external repository URI."""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", ref_path):
        return True
    return bool(re.match(r"^[^@\s]+@[^:\s]+:.+$", ref_path))


def _strip_git_suffix(path: str) -> str:
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path


def _normalize_git_remote(remote: str) -> ExternalRepoTarget | None:
    """Normalize equivalent git remote strings for matching local checkouts."""
    raw = remote.strip()
    if not raw:
        return None

    scp_match = re.match(r"^(?P<user>[^@\s]+)@(?P<host>[^:\s]+):(?P<path>.+)$", raw)
    if scp_match:
        host = scp_match.group("host").lower()
        repo_path = _strip_git_suffix(scp_match.group("path")).lower()
        return ExternalRepoTarget(
            raw=raw,
            normalized=f"git:{host}/{repo_path}",
            clone_url=raw,
        )

    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme in {"http", "https", "ssh"} and parsed.netloc:
        host = parsed.hostname.lower() if parsed.hostname else parsed.netloc.lower()
        repo_path = urllib.parse.unquote(parsed.path).lstrip("/")
        repo_path = _strip_git_suffix(repo_path).lower()
        return ExternalRepoTarget(
            raw=raw,
            normalized=f"git:{host}/{repo_path}",
            clone_url=raw,
        )

    if parsed.scheme == "file":
        direct_path = Path(urllib.parse.unquote(parsed.path)).expanduser()
        return ExternalRepoTarget(
            raw=raw,
            normalized=f"file:{direct_path.resolve()}",
            clone_url=raw,
            direct_path=direct_path,
        )

    return None


def _normalizes_to_same_remote(left: str, right: str) -> bool:
    left_target = _normalize_git_remote(left)
    right_target = _normalize_git_remote(right)
    if left_target is None or right_target is None:
        return False
    return left_target.normalized == right_target.normalized


def _external_repo_candidate_sort_key(
    candidate: Path, target: ExternalRepoTarget
) -> tuple[int, str, str]:
    repo_name = target.normalized.rsplit("/", 1)[-1]
    candidate_name = candidate.name.lower()
    if candidate_name == repo_name:
        checkout_rank = 0
    elif re.fullmatch(rf"{re.escape(repo_name)}_\d+", candidate_name):
        checkout_rank = 2
    else:
        checkout_rank = 1
    return checkout_rank, candidate_name, str(candidate)


def _iter_external_repo_candidates(
    git_root: Path, external_repo_paths: list[Path], target: ExternalRepoTarget
) -> list[Path]:
    """Return explicit and nearby directories that may contain external repos."""
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            return
        if resolved in seen or not resolved.is_dir():
            return
        seen.add(resolved)
        candidates.append(resolved)

    for candidate in external_repo_paths:
        add(candidate)

    nearby_candidates = [git_root.parent]
    try:
        for sibling in git_root.parent.iterdir():
            if sibling == git_root:
                continue
            if sibling.is_dir():
                nearby_candidates.append(sibling)
    except OSError:
        pass

    for candidate in sorted(
        nearby_candidates,
        key=lambda path: _external_repo_candidate_sort_key(path, target),
    ):
        add(candidate)

    return candidates


def _cache_dir_for_external_repo(target: ExternalRepoTarget) -> Path:
    cache_root = Path(
        os.environ.get(
            "SYMVISION_EXTERNAL_REPO_CACHE",
            str(Path.home() / ".cache" / "symvision" / "external-repos"),
        )
    ).expanduser()
    digest = hashlib.sha256(target.normalized.encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", target.normalized).strip("-")
    return cache_root / f"{slug[:64]}-{digest}"


def resolve_external_repo_roots(
    ref_path: str, git_root: Path, external_repo_paths: list[Path]
) -> tuple[list[Path], str | None]:
    """Resolve an external repository pragma to ordered local git checkouts."""
    target = _normalize_git_remote(ref_path)
    if target is None:
        return [], f"unsupported external repository URI '{ref_path}'"

    if target.direct_path is not None:
        direct_root = get_git_root(target.direct_path)
        if direct_root is not None:
            return [direct_root], None
        return [], f"could not resolve external repository '{ref_path}'"

    matching_roots: list[Path] = []
    seen_roots: set[Path] = set()
    for candidate in _iter_external_repo_candidates(git_root, external_repo_paths, target):
        candidate_root = get_git_root(candidate)
        if candidate_root is None:
            continue
        try:
            resolved_root = candidate_root.resolve()
        except OSError:
            continue
        if resolved_root in seen_roots:
            continue
        origin = get_git_origin(candidate_root)
        if origin and _normalizes_to_same_remote(origin, ref_path):
            seen_roots.add(resolved_root)
            matching_roots.append(candidate_root)

    if matching_roots:
        return matching_roots, None

    if target.clone_url is None or shutil.which("git") is None:
        return [], f"could not resolve external repository '{ref_path}'"

    cache_dir = _cache_dir_for_external_repo(target)
    if cache_dir.exists():
        cached_root = get_git_root(cache_dir)
        cached_origin = get_git_origin(cache_dir) if cached_root else None
        if cached_root and cached_origin and _normalizes_to_same_remote(cached_origin, ref_path):
            return [cached_root], None
        return [], (
            f"external repository cache path '{cache_dir}' exists but does not match '{ref_path}'"
        )

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", target.clone_url, str(cache_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        return [], f"could not fetch external repository '{ref_path}'{suffix}"

    cloned_root = get_git_root(cache_dir)
    if cloned_root is None:
        return [], f"could not resolve external repository '{ref_path}'"
    return [cloned_root], None


def _external_python_references_symbol(
    symbol_name: str,
    external_python_files: list[Path],
    tracked_modules: set[str],
) -> bool:
    file_infos: list[FileInfo] = []
    for py_file in external_python_files:
        info = extract_file_info(py_file)
        if info is not None:
            file_infos.append(info)
    return symbol_name in batch_search_usage({symbol_name}, file_infos, tracked_modules)


def _external_text_references_symbol(symbol_name: str, tracked_files: list[Path]) -> bool:
    pattern = re.compile(rf"\b{re.escape(symbol_name)}\b")
    for file_path in tracked_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if pattern.search(content):
            return True
    return False


def external_repo_references_symbol(
    symbol_name: str, external_repo_root: Path, tracked_modules: set[str]
) -> bool:
    tracked_files = [path for path in find_git_tracked_files(external_repo_root) if path.is_file()]
    non_test_files = [
        path
        for path in tracked_files
        if not is_test_support_file_path(path.relative_to(external_repo_root))
    ]
    python_files = [path for path in non_test_files if path.suffix == ".py"]
    text_files = [path for path in non_test_files if path.suffix != ".py"]

    if _external_python_references_symbol(symbol_name, python_files, tracked_modules):
        return True
    return _external_text_references_symbol(symbol_name, text_files)
