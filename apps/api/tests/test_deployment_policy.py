# Purpose: verify the change-set path/content policy.
# Responsibilities: allow safe paths under the allowlist; reject protected patterns, traversal,
#   absolute/home paths, executable and binary targets; enforce file/byte ceilings.
from __future__ import annotations

import pytest

from app.services.deployment.policy import PathPolicy, PathPolicyError

_POLICY = PathPolicy(
    allowed_prefixes=("docs/", "config/decoys/", ".deceptiforge/"),
    protected_patterns=(".env", "secret", "credential", ".pem", ".github/workflows/"),
    max_files=3,
    max_bytes=1000,
)


@pytest.mark.parametrize(
    "path",
    ["docs/decoys/runbook.md", "config/decoys/service.yaml", ".deceptiforge/markers/a.md"],
)
def test_allowed_paths(path: str) -> None:
    _POLICY.check_path(path)  # does not raise
    assert _POLICY.allows(path)


@pytest.mark.parametrize(
    "path",
    [
        "docs/.env.example",  # protected pattern
        "config/decoys/db.secret",  # protected pattern
        "src/app.py",  # outside allowlist
        "/etc/passwd",  # absolute
        "~/secrets",  # home
        "docs/../../etc/x",  # traversal
        "docs/deploy.sh",  # executable
        "docs/logo.png",  # binary
        ".github/workflows/ci.yml",  # protected CI path (also outside allowlist)
    ],
)
def test_rejected_paths(path: str) -> None:
    assert not _POLICY.allows(path)
    with pytest.raises(PathPolicyError):
        _POLICY.check_path(path)


def test_totals_enforced() -> None:
    _POLICY.check_totals(3, 1000)  # exactly at the limits: ok
    with pytest.raises(PathPolicyError):
        _POLICY.check_totals(4, 100)
    with pytest.raises(PathPolicyError):
        _POLICY.check_totals(1, 1001)
