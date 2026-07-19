# Purpose: enforce the change-set path/content policy that keeps decoy deployments safe.
# Responsibilities: validate a target path against the allowlist and protected patterns, reject
#   binary/executable/symlink-shaped targets and path traversal, and enforce per-deployment file and
#   byte ceilings. Pure and deterministic. Dependencies: Settings.
from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings

_EXECUTABLE_SUFFIXES = frozenset(
    {".sh", ".bash", ".zsh", ".exe", ".bin", ".dll", ".so", ".dylib", ".com", ".bat",
     ".cmd", ".ps1"}
)
_BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz", ".jar", ".class", ".o",
     ".a", ".wasm", ".woff", ".woff2", ".ico"}
)


class PathPolicyError(Exception):
    """Raised when a target path or change set violates deployment policy."""


@dataclass(frozen=True)
class PathPolicy:
    allowed_prefixes: tuple[str, ...]
    protected_patterns: tuple[str, ...]
    max_files: int
    max_bytes: int

    @classmethod
    def from_settings(cls, settings: Settings) -> PathPolicy:
        return cls(
            allowed_prefixes=tuple(settings.decoy_allowed_path_prefixes),
            protected_patterns=tuple(p.lower() for p in settings.decoy_protected_path_patterns),
            max_files=settings.decoy_max_files_per_deployment,
            max_bytes=settings.decoy_max_bytes_per_deployment,
        )

    def check_path(self, path: str) -> None:
        """Raise PathPolicyError if ``path`` may not be written by a deployment."""
        lowered = path.lower()
        if not path or len(path) > 2048:
            raise PathPolicyError("empty or over-long target path")
        if path.startswith("/") or path.startswith("~") or "\\" in path or "\x00" in path:
            raise PathPolicyError("absolute, home, or non-portable path is not allowed")
        if ".." in path.split("/"):
            raise PathPolicyError("path traversal is not allowed")
        if any(pattern in lowered for pattern in self.protected_patterns):
            raise PathPolicyError("target matches a protected path pattern")
        if not any(path.startswith(prefix) for prefix in self.allowed_prefixes):
            raise PathPolicyError("target is outside the allowed path prefixes")
        suffix = _suffix(path)
        if suffix in _EXECUTABLE_SUFFIXES:
            raise PathPolicyError("executable file targets are not permitted")
        if suffix in _BINARY_SUFFIXES:
            raise PathPolicyError("binary file targets are not permitted")

    def allows(self, path: str) -> bool:
        try:
            self.check_path(path)
        except PathPolicyError:
            return False
        return True

    def check_totals(self, file_count: int, total_bytes: int) -> None:
        if file_count > self.max_files:
            raise PathPolicyError(f"too many changed files ({file_count} > {self.max_files})")
        if total_bytes > self.max_bytes:
            raise PathPolicyError(f"change set too large ({total_bytes} > {self.max_bytes} bytes)")


def _suffix(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""
