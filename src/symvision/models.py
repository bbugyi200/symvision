"""Shared data models for symvision analysis."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PragmaInfo:
    """A pragma attached to a symbol definition."""

    symbol_name: str
    ref_path: str
    source_file: Path
    pragma_line: int


@dataclass
class FileInfo:
    """Information extracted from a Python file in one AST pass."""

    path: Path
    content: str
    public_symbols: list[str] = field(default_factory=list)
    private_symbols: list[str] = field(default_factory=list)
    pragmas: dict[str, list[PragmaInfo]] = field(default_factory=dict)
    private_def_lines: dict[str, int] = field(default_factory=dict)
    import_candidates: set[str] = field(default_factory=set)
    module_aliases: dict[str, set[str]] = field(default_factory=dict)
    attribute_chains: list[tuple[str, ...]] = field(default_factory=list)
    api_dependency_candidates: dict[str, set[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ExternalRepoTarget:
    """Normalized representation of an external repository reference."""

    raw: str
    normalized: str
    clone_url: str | None
    direct_path: Path | None = None
