"""Small git query helpers."""

import subprocess
from pathlib import Path


def get_git_root(directory: Path | None = None) -> Path | None:
    """Get the git repository root directory."""
    cmd = ["git"]
    if directory is not None:
        cmd.extend(["-C", str(directory)])
    cmd.extend(["rev-parse", "--show-toplevel"])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def get_git_origin(directory: Path) -> str | None:
    """Return a git repository's origin URL, if one is configured."""
    result = subprocess.run(
        ["git", "-C", str(directory), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
