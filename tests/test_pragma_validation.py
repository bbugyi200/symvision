"""Focused validation tests for local pragma edge cases."""

from pathlib import Path

import pytest

from symvision.models import PragmaInfo
from symvision.pragmas import validate_pragmas


def _pragma(name: str, ref_path: str, source: Path) -> dict[str, list[PragmaInfo]]:
    return {
        name: [
            PragmaInfo(
                symbol_name=name,
                ref_path=ref_path,
                source_file=source,
                pragma_line=1,
            )
        ]
    }


@pytest.mark.parametrize(
    ("name", "ref_path", "imported", "message"),
    [
        ("_private", "config.toml", set(), "cannot be applied to private symbol"),
        ("Public", "config.toml", {"Public"}, "already imported by other Python files"),
        ("Public", "missing.toml", set(), "does not exist"),
        ("Public", "src/config.toml", set(), "is inside src/"),
        ("Public", "config.toml", set(), "does not contain a reference"),
    ],
)
def test_local_pragma_validation_errors(
    tmp_path: Path,
    name: str,
    ref_path: str,
    imported: set[str],
    message: str,
) -> None:
    source = tmp_path / "src/pkg/core.py"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")
    if ref_path in {"config.toml", "src/config.toml"}:
        path = tmp_path / ref_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("unrelated = true\n", encoding="utf-8")

    errors = validate_pragmas(
        _pragma(name, ref_path, source),
        tmp_path,
        imported,
        set(),
        [],
        set(),
    )

    assert len(errors) == 1
    assert message in errors[0]
