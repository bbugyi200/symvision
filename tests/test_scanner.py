"""Focused AST scanner tests."""

from pathlib import Path
from typing import Any

from symvision.models import FileInfo
from symvision.scanner import batch_check_private_in_file, batch_search_usage, extract_file_info


def test_extracts_pragmas_decorators_and_api_dependencies(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text(
        "import decorators as deco\n"
        "from typing import Any\n\n"
        "class Base:\n    pass\n\n"
        "# symvision: config/secondary.toml\n"
        "# symvision: config/primary.toml\n"
        "@deco.generated(option=True)\n"
        "class Record(Base):\n    field: Any\n\n"
        "async def build(value: Record, *args: Base, **kwargs: Any) -> Record:\n"
        "    return Record()\n\n"
        "def _private():\n    return 1\n",
        encoding="utf-8",
    )

    info = extract_file_info(source)
    excluded = extract_file_info(source, {"deco"})

    assert info is not None
    assert info.public_symbols == ["Base", "Record", "build"]
    assert info.private_symbols == ["_private"]
    assert [pragma.ref_path for pragma in info.pragmas["Record"]] == [
        "config/primary.toml",
        "config/secondary.toml",
    ]
    assert info.api_dependency_candidates["Record"] == {"Base"}
    assert info.api_dependency_candidates["build"] == {"Any", "Base", "Record"}
    assert excluded is not None
    assert "Record" not in excluded.public_symbols


def test_handles_syntax_errors_and_missing_files(tmp_path: Path, capsys: Any) -> None:
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")

    assert extract_file_info(invalid) is None
    assert extract_file_info(tmp_path / "missing.py") is None
    assert "Warning: Could not parse" in capsys.readouterr().err


def test_batch_usage_tracks_import_and_nested_module_aliases(tmp_path: Path) -> None:
    source = tmp_path / "consumer.py"
    source.write_text(
        "import pkg.facade\n"
        "import pkg.records as records\n"
        "from pkg.direct import Direct as Alias\n"
        "from . import Relative\n"
        "from pkg.star import *\n\n"
        "pkg.facade.Widget()\nrecords.Record()\nAlias()\n",
        encoding="utf-8",
    )
    info = extract_file_info(source)
    assert info is not None

    found = batch_search_usage(
        {"Direct", "Widget", "Record", "Missing"},
        [info],
        {"pkg.facade", "pkg.records"},
    )

    assert found == {"Direct", "Widget", "Record"}
    assert batch_search_usage(set(), [info]) == set()


def test_private_usage_check_distinguishes_definition_line() -> None:
    info = FileInfo(
        path=Path("module.py"),
        content="def _used():\n    return 1\n\nvalue = _used()\n\ndef _unused():\n    return 2\n",
        private_symbols=["_used", "_unused"],
        private_def_lines={"_used": 1, "_unused": 6},
    )

    assert batch_check_private_in_file(info) == (["_used"], ["_unused"])
