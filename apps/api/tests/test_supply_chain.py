# Purpose: guard the supply-chain posture so a release cannot silently lose pinning, scanning, or
#   dependency-group separation. File-content checks; no network.
from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "apps" / "api"


def _ci() -> str:
    return (REPO / ".github" / "workflows" / "ci.yml").read_text()


def test_api_base_image_is_pinned_by_digest() -> None:
    dockerfile = (API / "Dockerfile").read_text()
    assert re.search(
        r"^FROM .+@sha256:[0-9a-f]{64}", dockerfile, re.MULTILINE
    ), "the API base image must be pinned by immutable digest"


def test_no_floating_latest_tags_in_build_files() -> None:
    for path in (API / "Dockerfile", REPO / "docker-compose.yml"):
        text = path.read_text()
        assert ":latest" not in text, f"{path.name} must not use a floating :latest tag"


def test_github_actions_are_pinned_to_commit_shas() -> None:
    """A mutable action tag is a supply-chain foothold; every `uses:` must carry a 40-char SHA."""
    for line in _ci().splitlines():
        stripped = line.strip()
        if stripped.startswith("- uses:") or stripped.startswith("uses:"):
            ref = stripped.split("uses:", 1)[1].split("#", 1)[0].strip()
            assert re.search(r"@[0-9a-f]{40}$", ref), f"unpinned action: {ref}"


def test_runtime_and_dev_dependency_groups_are_distinct() -> None:
    data = tomllib.loads((API / "pyproject.toml").read_text())
    runtime = {re.split(r"[><=\[]", d)[0] for d in data["project"]["dependencies"]}
    dev = {re.split(r"[><=\[]", d)[0] for d in data["project"]["optional-dependencies"]["dev"]}
    assert runtime & dev == set(), "a package must not appear in both runtime and dev groups"
    # Test tooling must never leak into the shipped runtime set.
    assert {"pytest", "ruff", "mypy", "black"} & runtime == set()


def test_runtime_dependencies_are_upper_bounded() -> None:
    """An unbounded range lets a future major version enter a release unreviewed."""
    data = tomllib.loads((API / "pyproject.toml").read_text())
    for dependency in data["project"]["dependencies"]:
        assert "<" in dependency, f"unbounded runtime dependency: {dependency}"


def test_ci_runs_vulnerability_scanning_and_sbom() -> None:
    ci = _ci()
    for expected in (
        "Runtime dependency audit (blocking)",
        "JavaScript dependency audit (blocking, production)",
        "Scan API image (Trivy)",
        "Generate SBOMs (CycloneDX)",
        "Assert SBOMs contain no secret material",
        "Stamp SBOMs with the build revision",
    ):
        assert expected in ci, f"CI is missing: {expected}"


def test_scanner_exceptions_are_documented_not_blanket() -> None:
    """An exceptions file may exist, but it must never contain a wildcard suppression."""
    for name in (".trivyignore", ".pip-audit-ignore"):
        path = REPO / name
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            assert entry != "*" and "*" not in entry, f"{name} must not contain a wildcard"


def test_local_agent_state_is_ignored() -> None:
    assert ".claude/" in (REPO / ".gitignore").read_text()
