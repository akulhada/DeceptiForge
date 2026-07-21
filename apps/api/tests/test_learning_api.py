# Purpose: verify the learning HTTP surface and offline job — flag gating, permission and
#   separation-of-duties enforcement, organization isolation, feedback bounds/idempotency, the
#   promotion/rollback workflow, and that no request path mutates active weights.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models.domain.learning import ModelStatus, OutcomeType
from app.repositories.learning import LearningRepository
from app.services.api_keys import ApiKeyService


def _key(client, org: str, role: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), role, role)
    session.commit()
    session.close()
    return plaintext


def _headers(key: str, org: str) -> dict[str, str]:
    return {"X-DeceptiForge-API-Key": key, "X-DeceptiForge-Org-Id": org}


def _client(make_client, *, learning: bool = True):  # type: ignore[no-untyped-def]
    return make_client(
        demo_enabled=False, auth_enabled=True, app_env="development", learning_enabled=learning
    )


def _seed_candidate(client, org: str, *, requester: UUID | None = None) -> UUID:  # type: ignore[no-untyped-def]
    """Create a candidate version directly so lifecycle routes have something to act on."""
    from app.models.domain.learning import (
        CalibrationMetrics,
        CalibrationReport,
        CalibrationWeights,
    )

    session = client.app_session()
    repository = LearningRepository(session, UUID(org))
    now = datetime.now(UTC)
    report = CalibrationReport(
        methodology_version="calibration-v1",
        feature_schema_version="features-v1",
        training_window_start=now - timedelta(days=30),
        training_window_end=now,
        included_event_count=60,
        excluded_event_count=0,
        candidate_weights=CalibrationWeights(zone_priors={"payment": 0.7}),
        metrics=CalibrationMetrics(),
    )
    record = repository.create_candidate(
        report,
        algorithm_name="placement-prior-calibration",
        algorithm_version="1.0",
        requested_by_actor_id=requester,
    )
    version_id = record.id
    session.commit()
    session.close()
    return version_id


_FEEDBACK = {"feedback_type": "false_positive", "comment": "looked benign"}


# ---- gating + permissions ------------------------------------------------------------------------


def test_routes_absent_when_learning_disabled(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client, learning=False) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        r = client.post(f"/alerts/{uuid4()}/feedback", json=_FEEDBACK, headers=_headers(key, org))
        assert r.status_code == 404


def test_feedback_requires_authentication(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        r = client.post(f"/alerts/{uuid4()}/feedback", json=_FEEDBACK)
        assert r.status_code == 401


def test_viewer_cannot_submit_feedback(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "viewer")
        r = client.post(f"/alerts/{uuid4()}/feedback", json=_FEEDBACK, headers=_headers(key, org))
        assert r.status_code == 403


def test_analyst_cannot_approve_or_activate(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        version_id = _seed_candidate(client, org)
        key = _key(client, org, "analyst")
        for action in ("approve", "activate"):
            r = client.post(
                f"/learning/model-versions/{version_id}/{action}", headers=_headers(key, org)
            )
            assert r.status_code == 403


def test_admin_may_calibrate_but_not_approve_or_activate(make_client) -> None:  # type: ignore[no-untyped-def]
    """Separation of duties: candidate generation and approval are different roles."""
    with _client(make_client) as client:
        org = str(uuid4())
        version_id = _seed_candidate(client, org)
        key = _key(client, org, "admin")
        assert (
            client.post("/learning/calibration-runs", headers=_headers(key, org)).status_code == 200
        )
        for action in ("approve", "activate"):
            r = client.post(
                f"/learning/model-versions/{version_id}/{action}", headers=_headers(key, org)
            )
            assert r.status_code == 403


# ---- analyst feedback ----------------------------------------------------------------------------


def test_feedback_recorded_and_does_not_change_active_weights(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        r = client.post(f"/alerts/{uuid4()}/feedback", json=_FEEDBACK, headers=_headers(key, org))
        assert r.status_code == 200
        body = r.json()
        assert body["recorded"] is True
        assert body["active_weights_changed"] is False
        # No version became active from a single feedback event.
        read_key = _key(client, org, "viewer")
        metrics = client.get("/learning/metrics", headers=_headers(read_key, org)).json()
        assert metrics["active_version_id"] is None


def test_duplicate_feedback_is_idempotent(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        target = uuid4()
        first = client.post(
            f"/alerts/{target}/feedback", json=_FEEDBACK, headers=_headers(key, org)
        ).json()
        second = client.post(
            f"/alerts/{target}/feedback", json=_FEEDBACK, headers=_headers(key, org)
        ).json()
        assert first["id"] == second["id"]
        assert second["revision"] == 1


def test_changed_feedback_creates_a_revision_not_an_overwrite(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        target = uuid4()
        client.post(f"/alerts/{target}/feedback", json=_FEEDBACK, headers=_headers(key, org))
        revised = client.post(
            f"/alerts/{target}/feedback",
            json={"feedback_type": "confirmed_incident"},
            headers=_headers(key, org),
        ).json()
        assert revised["revision"] == 2


def test_comment_is_sanitized_and_bounded(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        target = uuid4()
        client.post(
            f"/alerts/{target}/feedback",
            json={
                "feedback_type": "false_positive",
                "comment": "check /etc/passwd and API_KEY=abc at https://x.example " + "x" * 900,
            },
            headers=_headers(key, org),
        )
        session = client.app_session()
        stored = LearningRepository(session, UUID(org)).feedback_for_target("alert", target)
        comment = stored[0].normalized_comment or ""
        session.close()
        assert len(comment) <= 500
        assert "/etc/passwd" not in comment and "://" not in comment


def test_invalid_feedback_type_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        r = client.post(
            f"/alerts/{uuid4()}/feedback",
            json={"feedback_type": "not_a_real_type"},
            headers=_headers(key, org),
        )
        assert r.status_code == 422


# ---- lifecycle -----------------------------------------------------------------------------------


def test_candidate_cannot_be_activated_without_approval(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        version_id = _seed_candidate(client, org)
        key = _key(client, org, "owner")
        r = client.post(
            f"/learning/model-versions/{version_id}/activate", headers=_headers(key, org)
        )
        assert r.status_code == 409


def test_full_promotion_then_rollback(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        version_id = _seed_candidate(client, org)
        key = _key(client, org, "owner")
        headers = _headers(key, org)
        assert (
            client.post(
                f"/learning/model-versions/{version_id}/submit-review", headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/learning/model-versions/{version_id}/approve", headers=headers
            ).status_code
            == 200
        )
        activated = client.post(f"/learning/model-versions/{version_id}/activate", headers=headers)
        assert activated.status_code == 200
        assert activated.json()["status"] == ModelStatus.ACTIVE.value
        rolled = client.post(
            f"/learning/model-versions/{version_id}/rollback",
            json={"reason": "confidence regression"},
            headers=headers,
        )
        assert rolled.status_code == 200
        assert rolled.json()["status"] == ModelStatus.ROLLED_BACK.value


def test_rollback_requires_a_reason(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        version_id = _seed_candidate(client, org)
        key = _key(client, org, "owner")
        r = client.post(
            f"/learning/model-versions/{version_id}/rollback",
            json={"reason": ""},
            headers=_headers(key, org),
        )
        assert r.status_code == 422


def test_self_approval_blocked_by_separation_of_duties(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        session = client.app_session()
        record, plaintext = ApiKeyService(session).create(UUID(org), "owner", "owner")
        actor_id = record.id
        session.commit()
        session.close()
        version_id = _seed_candidate(client, org, requester=actor_id)
        headers = _headers(plaintext, org)
        client.post(f"/learning/model-versions/{version_id}/submit-review", headers=headers)
        r = client.post(f"/learning/model-versions/{version_id}/approve", headers=headers)
        assert r.status_code == 409
        assert "separation of duties" in r.json()["detail"]


# ---- isolation -----------------------------------------------------------------------------------


def test_other_organization_version_is_not_visible(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org_a, org_b = str(uuid4()), str(uuid4())
        version_id = _seed_candidate(client, org_a)
        key_b = _key(client, org_b, "owner")
        r = client.get(f"/learning/model-versions/{version_id}", headers=_headers(key_b, org_b))
        assert r.status_code == 404  # not 403: existence is not confirmed to another tenant


def test_cross_organization_activation_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org_a, org_b = str(uuid4()), str(uuid4())
        version_id = _seed_candidate(client, org_a)
        key_b = _key(client, org_b, "owner")
        r = client.post(
            f"/learning/model-versions/{version_id}/activate", headers=_headers(key_b, org_b)
        )
        assert r.status_code == 404


def test_version_list_only_returns_own_organization(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org_a, org_b = str(uuid4()), str(uuid4())
        _seed_candidate(client, org_a)
        key_b = _key(client, org_b, "owner")
        listed = client.get("/learning/model-versions", headers=_headers(key_b, org_b)).json()
        assert listed == []


# ---- repository-level guarantees -----------------------------------------------------------------


def test_outcomes_are_idempotent_and_org_scoped(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org_a, org_b = uuid4(), uuid4()
        session = client.app_session()
        repo_a = LearningRepository(session, org_a)
        recommendation = repo_a.record_recommendation(
            snapshot_id=None,
            recommendation_type="placement",
            target_zone="payment",
            decoy_type="secret",
            rank=1,
            confidence=0.8,
            reasoning_codes=("evidence",),
            engine_version="1.0",
        )
        first = repo_a.record_outcome(recommendation.id, OutcomeType.ACCEPTED)
        second = repo_a.record_outcome(recommendation.id, OutcomeType.ACCEPTED)
        assert first.id == second.id  # idempotent

        repo_b = LearningRepository(session, org_b)
        try:
            repo_b.record_outcome(recommendation.id, OutcomeType.ACCEPTED)
            raise AssertionError("cross-organization outcome must be rejected")
        except PermissionError:
            pass
        session.close()


def test_calibration_job_is_inert_when_learning_disabled() -> None:
    """The offline job cannot create or activate anything while the feature is off."""
    from app.config.settings import Settings
    from app.jobs.learning_calibration import run

    result = run(Settings(learning_enabled=False))
    assert result == {"organizations": 0, "candidates": 0, "skipped_insufficient": 0}
