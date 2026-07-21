# Purpose: verify deterministic preview generation and safety filtering.
# Responsibilities: only accepted + policy-allowed + inert assets become change-set items; rendered
#   content is deterministic and marker-bearing; the preview hash is stable; limits are enforced.
from __future__ import annotations

from uuid import uuid4

import pytest
from _deploy_factories import make_asset, make_plan, make_report

from app.models.domain.decoy import BelievabilityDecision
from app.services.deployment.policy import PathPolicy, PathPolicyError
from app.services.deployment.preview import PreviewError, build_preview
from app.services.deployment.rendering import deployment_marker

_POLICY = PathPolicy(
    allowed_prefixes=("docs/", "config/decoys/"),
    protected_patterns=(".env", "secret", "credential"),
    max_files=10,
    max_bytes=100_000,
)


def _build(plan, reports, deployment_id=None, base="abc123"):  # type: ignore[no-untyped-def]
    return build_preview(
        deployment_id=deployment_id or uuid4(),
        repository_id=uuid4(),
        base_branch="main",
        base_commit_sha=base,
        target_branch="deceptiforge/decoy-x",
        plan=plan,
        reports=reports,
        policy=_POLICY,
        expires_at=None,
    )


def test_preview_includes_only_accepted_allowed_assets() -> None:
    good = make_asset("docs/decoys/runbook.md")
    protected = make_asset("docs/.env.local")  # protected pattern
    outside = make_asset("src/app.py")  # outside allowlist
    rejected_report = make_asset("docs/decoys/warn.md")  # report is REJECT
    plan = make_plan(good, protected, outside, rejected_report)
    reports = (
        make_report(good.decoy_id),
        make_report(protected.decoy_id),
        make_report(outside.decoy_id),
        make_report(rejected_report.decoy_id, BelievabilityDecision.REJECT),
    )
    preview, contents = _build(plan, reports)

    assert preview.changed_files == 1
    assert preview.items[0].target_path == "docs/decoys/runbook.md"
    assert good.decoy_id in contents
    # The three unsafe assets are surfaced as warnings, not silently dropped.
    assert len(preview.warnings) == 3


def test_rendered_content_is_deterministic_and_marked() -> None:
    asset = make_asset("docs/decoys/runbook.md", decoy_id=uuid4())
    plan = make_plan(asset)
    reports = (make_report(asset.decoy_id),)
    p1, c1 = _build(plan, reports, base="sha1")
    p2, c2 = _build(plan, reports, base="sha1")
    assert c1 == c2
    assert p1.preview_hash == p2.preview_hash  # deterministic
    body = c1[asset.decoy_id]
    assert deployment_marker(asset.decoy_id) in body
    assert "no real secrets" in body.lower()
    # Content hash in the item matches the rendered body.
    from app.services.deployment.rendering import content_sha256

    assert p1.items[0].proposed_content_hash == content_sha256(body)


def test_preview_hash_changes_with_base_commit() -> None:
    asset = make_asset("docs/decoys/runbook.md")
    plan = make_plan(asset)
    reports = (make_report(asset.decoy_id),)
    a, _ = _build(plan, reports, base="commitA")
    b, _ = _build(plan, reports, base="commitB")
    assert a.preview_hash != b.preview_hash  # drift in base commit invalidates the preview


def test_no_deployable_assets_raises() -> None:
    asset = make_asset("src/secret.py")  # protected + outside allowlist
    plan = make_plan(asset)
    reports = (make_report(asset.decoy_id),)
    with pytest.raises(PreviewError):
        _build(plan, reports)


def test_file_count_limit_enforced() -> None:
    tight = PathPolicy(("docs/",), (".env",), max_files=1, max_bytes=100_000)
    a1 = make_asset("docs/a.md")
    a2 = make_asset("docs/b.md")
    plan = make_plan(a1, a2)
    reports = (make_report(a1.decoy_id), make_report(a2.decoy_id))
    with pytest.raises(PathPolicyError):
        build_preview(
            deployment_id=uuid4(),
            repository_id=uuid4(),
            base_branch="main",
            base_commit_sha="x",
            target_branch="t",
            plan=plan,
            reports=reports,
            policy=tight,
            expires_at=None,
        )
