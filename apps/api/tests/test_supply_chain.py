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


def test_production_compose_postgres_has_a_healthcheck() -> None:
    """Every service waits on `condition: service_healthy`; without this the stack cannot start."""
    compose = (REPO / "docker-compose.prod.example.yml").read_text()
    assert "pg_isready" in compose, "postgres must define a real healthcheck"
    # And the dependency it satisfies must still be declared.
    assert "condition: service_healthy" in compose


def test_every_service_awaited_as_healthy_defines_a_healthcheck() -> None:
    import yaml

    doc = yaml.safe_load((REPO / "docker-compose.prod.example.yml").read_text())
    services = doc["services"]
    awaited: set[str] = set()
    for service in services.values():
        depends = service.get("depends_on") or {}
        if isinstance(depends, dict):
            for name, spec in depends.items():
                if isinstance(spec, dict) and spec.get("condition") == "service_healthy":
                    awaited.add(name)
    for name in awaited:
        assert (
            "healthcheck" in services[name]
        ), f"{name} is awaited as service_healthy but defines no healthcheck"


def test_no_document_claims_legal_hold_preservation() -> None:
    """Legal holds are not implemented; documentation must not claim they survive retention.

    A claim of preservation while retention jobs can delete the records is an operational defect,
    not stale prose. Delete this test only when holds are genuinely enforced end to end.
    """
    claims = (
        "legal holds survive",
        "legal holds are preserved",
        "legal hold is enforced",
        "legal holds are enforced",
    )
    for path in (REPO / "docs").rglob("*.md"):
        lowered = path.read_text().lower()
        for claim in claims:
            assert claim not in lowered, f"{path.name} claims unimplemented legal-hold behaviour"


def test_restore_drill_makes_no_legal_hold_claim() -> None:
    source = (API / "app" / "services" / "reliability" / "restore_verify.py").read_text()
    assert (
        '_check("legal_holds_present"' not in source
    ), "the restore drill must not emit a passing legal-hold check while holds are unimplemented"


def test_service_images_are_pinned_by_digest() -> None:
    """A mutable tag lets a rebuild pull different database or cache contents."""
    compose = (REPO / "docker-compose.prod.example.yml").read_text()
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped.startswith("image:"):
            reference = stripped.split("image:", 1)[1].strip()
            assert "@sha256:" in reference, f"unpinned image: {reference}"


def test_sbom_generator_is_pinned() -> None:
    ci = _ci()
    assert "@latest" not in ci, "CI must not resolve a tool at build time via @latest"


def test_analysis_lab_flags_cannot_drift_apart() -> None:
    """The lab has two independent flags; a deployment must not enable one without the other.

    The backend refuses ANALYSIS_LAB_ENABLED outside development, but the NEXT_PUBLIC_ flag is
    baked into the web build and the API cannot police it. The frontend page must therefore gate on
    its own flag, and no committed environment template may turn it on.
    """
    page = (REPO / "apps" / "web" / "app" / "analysis-lab" / "page.tsx").read_text()
    assert "NEXT_PUBLIC_ANALYSIS_LAB_ENABLED" in page
    assert "notFound()" in page, "the route must 404 when disabled, not merely hide navigation"

    for template in REPO.rglob(".env*.example"):
        for line in template.read_text().splitlines():
            entry = line.strip()
            if entry.startswith("NEXT_PUBLIC_ANALYSIS_LAB_ENABLED"):
                assert (
                    entry.split("=", 1)[1].strip().lower() != "true"
                ), f"{template} enables the analysis lab by default"
