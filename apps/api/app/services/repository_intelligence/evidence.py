# Purpose: perform one bounded filesystem traversal and expose an immutable evidence bundle.
# Responsibilities: collect paths, extension counts, and bounded text fragments without persisting
#   raw source into any downstream profile. Dependencies: standard library only.
from __future__ import annotations

import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_SKIP_DIRS = frozenset({".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv"})
_TEXT_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".tf", ".sql"})
_MAX_FILES = 10_000
_MAX_TEXT_FILES = 200
_MAX_TEXT_BYTES = 20_000


@dataclass(frozen=True)
class FileEntry:
    """One discovered file, pre-parsed so analyzers never re-parse paths.

    path: repository-relative path in original case.
    name: basename in original case.
    suffix: lowercased suffix including the dot (for example ``.py``).
    """

    path: str
    name: str
    suffix: str


@dataclass(frozen=True)
class RepositoryEvidence:
    """Immutable output of a single crawl, consumed by every analyzer.

    It intentionally holds text fragments transiently in memory; a built profile never
    serializes them, preserving the no-source-retention security property.
    """

    root_path: str
    repository_name: str
    is_git_repository: bool
    files: tuple[FileEntry, ...]
    extension_counts: Mapping[str, int]
    text_fragments: tuple[str, ...]
    truncated: bool

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.files)


class RepositoryCrawler:
    """Single-pass, bounded local traversal.

    Purpose: gather every downstream analyzer's raw material in one I/O sweep.
    Complexity: O(files) time; O(bounded) space (<= max_text_files * max_text_bytes).
    Edge cases: unreadable files are skipped; traversal stops and flags ``truncated`` once
    ``max_files`` is reached; ignored directories are pruned before descent.
    """

    def __init__(
        self,
        *,
        max_files: int = _MAX_FILES,
        max_text_files: int = _MAX_TEXT_FILES,
        max_text_bytes: int = _MAX_TEXT_BYTES,
        skip_dirs: frozenset[str] = _SKIP_DIRS,
        text_suffixes: frozenset[str] = _TEXT_SUFFIXES,
    ) -> None:
        self._max_files = max_files
        self._max_text_files = max_text_files
        self._max_text_bytes = max_text_bytes
        self._skip_dirs = skip_dirs
        self._text_suffixes = text_suffixes

    def crawl(self, root: Path) -> RepositoryEvidence:
        root = Path(root).resolve()
        files: list[FileEntry] = []
        extensions: Counter[str] = Counter()
        fragments: list[str] = []
        truncated = False
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in self._skip_dirs]
            for filename in filenames:
                if len(files) >= self._max_files:
                    truncated = True
                    break
                path = Path(directory, filename)
                suffix = path.suffix.lower()
                files.append(
                    FileEntry(path=str(path.relative_to(root)), name=filename, suffix=suffix)
                )
                extensions[suffix] += 1
                if len(fragments) < self._max_text_files and suffix in self._text_suffixes:
                    try:
                        fragments.append(
                            path.read_text(encoding="utf-8", errors="ignore")[
                                : self._max_text_bytes
                            ]
                        )
                    except OSError:
                        continue
            if truncated:
                break
        return RepositoryEvidence(
            root_path=str(root),
            repository_name=root.name,
            is_git_repository=(root / ".git").exists(),
            files=tuple(files),
            extension_counts=dict(extensions),
            text_fragments=tuple(fragments),
            truncated=truncated,
        )
