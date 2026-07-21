# Purpose: verify SSRF endpoint validation, retry classification/backoff, payload-profile
#   minimization, and that canonical events carry no raw evidence.
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config.settings import Settings
from app.models.domain.integrations import EventType, PayloadProfile, RetryDecision
from app.models.domain.operations import Severity
from app.services.integrations import mapping, profiles, retry
from app.services.integrations.ssrf import SsrfError, validate_endpoint

_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _settings(**over) -> Settings:  # type: ignore[no-untyped-def]
    base = dict(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


# -- SSRF -------------------------------------------------------------------------------------


def test_ssrf_rejects_loopback_and_metadata_and_private() -> None:
    s = _settings(app_env="production")
    for url in (
        "https://127.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/",
        "https://10.0.0.5/hook",
        "https://[::1]/hook",
    ):
        with pytest.raises(SsrfError):
            validate_endpoint(url, s)


def test_ssrf_requires_https_outside_dev_and_no_credentials() -> None:
    with pytest.raises(SsrfError):
        validate_endpoint("http://example.com/hook", _settings(app_env="production"))
    with pytest.raises(SsrfError):
        validate_endpoint("https://user:pw@example.com/hook", _settings(app_env="production"))


def test_ssrf_allowlist_enforced(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Resolve allowlisted hosts to a fixed public IP so the test needs no network.
    monkeypatch.setattr(
        "app.services.integrations.ssrf.socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    s = _settings(app_env="production", security_export_allowed_domains=["siem.example.com"])
    assert validate_endpoint("https://siem.example.com/hook", s) == "siem.example.com"
    # A non-allowlisted host is rejected before DNS is even attempted.
    with pytest.raises(SsrfError):
        validate_endpoint("https://evil.example.net/hook", s)


# -- retry ------------------------------------------------------------------------------------


def test_retry_classification() -> None:
    assert retry.classify_status(200) == RetryDecision.SUCCESS
    assert retry.classify_status(500) == RetryDecision.RETRY
    assert retry.classify_status(429) == RetryDecision.RETRY
    assert retry.classify_status(408) == RetryDecision.RETRY
    assert retry.classify_status(401) == RetryDecision.PERMANENT
    assert retry.classify_status(400) == RetryDecision.PERMANENT
    assert retry.classify_transport_error() == RetryDecision.RETRY


def test_retry_after_and_backoff_monotonic() -> None:
    assert retry.parse_retry_after("30") == 30
    assert retry.parse_retry_after("bad") is None
    assert retry.backoff_seconds(1, key="k") < retry.backoff_seconds(5, key="k")
    # Deterministic given the same key + attempt.
    assert retry.backoff_seconds(3, key="k") == retry.backoff_seconds(3, key="k")


# -- profiles ---------------------------------------------------------------------------------


def _incident_event(narrative: str | None = None):  # type: ignore[no-untyped-def]
    return mapping.build_incident_event(
        event_type=EventType.INCIDENT_CREATED,
        org="org-1",
        occurred_at=_NOW,
        incident_id="i1",
        severity=Severity.HIGH,
        title="Incident",
        summary="a decoy was touched",
        confidence=0.9,
        incident_status="open",
        affected_surfaces=("repository",),
        evidence_summary="deterministic: 3 events across 1 surface",
        narrative=narrative,
    )


def test_minimal_profile_strips_detail() -> None:
    env = profiles.apply_profile(
        _incident_event(narrative="gpt narrative"),
        PayloadProfile.MINIMAL,
        include_narrative=True,
        max_bytes=65536,
    )
    assert env.summary == "" and env.narrative_summary is None
    assert env.affected_surfaces == () and env.deterministic_evidence_summary == ""


def test_narrative_only_when_allowed_and_labeled() -> None:
    with_narr = profiles.apply_profile(
        _incident_event(narrative="gpt narrative"),
        PayloadProfile.ANALYST,
        include_narrative=True,
        max_bytes=65536,
    )
    assert with_narr.narrative_summary == "gpt narrative"
    assert profiles.is_labeled_narrative(with_narr)
    without = profiles.apply_profile(
        _incident_event(narrative="gpt narrative"),
        PayloadProfile.ANALYST,
        include_narrative=False,
        max_bytes=65536,
    )
    assert without.narrative_summary is None


def test_payload_size_bound_enforced() -> None:
    env = profiles.apply_profile(
        _incident_event(narrative="x" * 2000),
        PayloadProfile.ANALYST,
        include_narrative=True,
        max_bytes=300,
    )
    assert len(env.model_dump_json().encode("utf-8")) <= 300 or env.narrative_summary is None


def test_canonical_event_has_no_raw_evidence() -> None:
    env = mapping.build_alert_event(
        event_type=EventType.ALERT_CREATED,
        org="org-1",
        occurred_at=_NOW,
        alert_id="a1",
        severity=Severity.HIGH,
        title="Alert",
        summary="decoy accessed",
        confidence=0.9,
        trace_ids=("DFAI-abc",),
        decoy_types=("rag_document",),
    )
    assert mapping.contains_no_raw_evidence(env)
