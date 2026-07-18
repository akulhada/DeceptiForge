# Purpose: verify the optional GPT incident-narrative layer and its deterministic fallback.
# Responsibilities: prove the context is minimized and stable, fallbacks trigger on missing/failed/
#   invalid model output, token truncation works, and the endpoint returns a narrative shape.
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import Settings
from app.models.domain.narrative import NarrativeSource, NarrativeStatus, TokenUsage
from app.models.domain.operations import (
    AlertEvidence,
    MonitorType,
    NormalizedAlert,
    Severity,
)
from app.services.incident_narrative import (
    IncidentNarrativeGenerator,
    ModelResult,
    NarrativeContextBuilder,
    context_hash,
)
from app.services.incident_reconstruction import IncidentReconstructionEngine

_DB_URL = "postgresql+psycopg://unused:unused@localhost/deceptiforge"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"_env_file": None, "database_url": _DB_URL}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _alert(
    trace: str, monitor: MonitorType, at: datetime, excerpt: str = "DFG-A"
) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="trace",
        summary="Decoy trace observed",
        source_monitor=monitor,
        confidence=0.9,
        first_seen=at,
        last_seen=at,
        event_count=1,
        deduplication_key=f"{trace}:id:{monitor.value}:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=excerpt, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def _incident(excerpt: str = "DFG-A", steps: int = 1):
    start = datetime.now(UTC)
    alerts = []
    for index in range(steps):
        alert = _alert("DFG-A", MonitorType.REPOSITORY, start + timedelta(seconds=index), excerpt)
        if alerts:
            alert = alert.model_copy(
                update={
                    "decoy_id": alerts[0].decoy_id,
                    "affected_placement_id": alerts[0].affected_placement_id,
                    "correlation_id": alerts[0].correlation_id,
                }
            )
        alerts.append(alert)
    return IncidentReconstructionEngine().reconstruct(tuple(alerts))[0]


class _OkClient:
    def complete(
        self, *, system: str, user: str, schema: dict[str, object], model: str
    ) -> ModelResult:
        body = {
            "executive_summary": "Possible exposure of a decoy secret.",
            "analyst_summary": "A decoy trace was observed in the repository.",
            "likely_sequence": ["Decoy read", "Trace observed"],
            "evidence_summary": ["repository match"],
            "recommended_next_actions": ["Review access logs"],
            "uncertainty_caveats": ["Not a confirmed breach"],
            "confidence_notes": "Aligned with deterministic confidence.",
        }
        return ModelResult(
            json_text=json.dumps(body),
            model=model,
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class _RaiseClient:
    def complete(self, **_: object) -> ModelResult:
        raise RuntimeError("upstream boom")


class _BadClient:
    def complete(self, **_: object) -> ModelResult:
        return ModelResult(json_text="{not valid json", model="m", token_usage=None)


def test_context_is_minimized_and_excludes_raw_payloads() -> None:
    long_excerpt = "S" * 200
    context = NarrativeContextBuilder().build(_incident(excerpt=long_excerpt))
    serialized = context.model_dump_json()

    assert all(len(step.evidence_excerpt) <= 120 for step in context.timeline)
    assert "S" not in serialized
    assert "surrounding content redacted" in serialized
    assert "payload" not in serialized


def test_context_hash_is_stable() -> None:
    incident = _incident()
    assert context_hash(NarrativeContextBuilder().build(incident)) == context_hash(
        NarrativeContextBuilder().build(incident)
    )


def test_token_budget_truncates_low_priority_timeline() -> None:
    context = NarrativeContextBuilder(token_budget=10).build(_incident(steps=3))

    assert context.truncated is True
    assert context.truncation_notes
    assert len(context.timeline) <= 2
    assert context.severity and context.recommended_actions  # preserved


def test_default_token_budget_compacts_long_deterministic_text() -> None:
    incident = _incident().model_copy(
        update={
            "root_cause_hypothesis": "R" * 10_000,
            "recommended_actions": ("A" * 2_000,) * 10,
            "correlation_reasons": ("C" * 2_000,) * 10,
        }
    )

    context = NarrativeContextBuilder().build(incident)

    assert len(context.model_dump_json()) // 4 <= 1_500
    assert context.truncated is True


def test_fallback_when_openai_not_configured() -> None:
    narrative = IncidentNarrativeGenerator(_settings(openai_api_key=None)).generate(
        _incident(), DEMO_ORGANIZATION_ID
    )

    assert narrative.source is NarrativeSource.FALLBACK
    assert narrative.status is NarrativeStatus.FALLBACK_DISABLED
    assert narrative.body.executive_summary
    assert narrative.body.recommended_next_actions


def test_model_success_produces_generated_narrative() -> None:
    narrative = IncidentNarrativeGenerator(
        _settings(openai_api_key="sk-test"), client=_OkClient()
    ).generate(_incident(), DEMO_ORGANIZATION_ID)

    assert narrative.source is NarrativeSource.MODEL
    assert narrative.status is NarrativeStatus.GENERATED
    assert narrative.token_usage is not None and narrative.token_usage.total_tokens == 15
    assert narrative.prompt_version == "incident-narrative-v1"


def test_model_failure_and_invalid_output_fall_back() -> None:
    failed = IncidentNarrativeGenerator(
        _settings(openai_api_key="sk-test"), client=_RaiseClient()
    ).generate(_incident(), DEMO_ORGANIZATION_ID)
    invalid = IncidentNarrativeGenerator(
        _settings(openai_api_key="sk-test"), client=_BadClient()
    ).generate(_incident(), DEMO_ORGANIZATION_ID)

    assert failed.status is NarrativeStatus.FALLBACK_ERROR and failed.error
    assert invalid.status is NarrativeStatus.FALLBACK_INVALID
    assert failed.source is NarrativeSource.FALLBACK and invalid.source is NarrativeSource.FALLBACK


def test_narrative_endpoint_returns_shape(client) -> None:
    client.post("/demo/seed")
    incidents = client.post("/demo/simulate-detection").json()["incidents"]
    incident_id = incidents[0]["incident_id"]

    assert client.get(f"/incidents/{incident_id}/narrative").status_code == 404

    generated = client.post(f"/incidents/{incident_id}/narrative")
    assert generated.status_code == 200
    body = generated.json()
    assert body["incident_id"] == incident_id
    assert body["source"] == "fallback"  # no OPENAI_API_KEY in tests
    assert body["body"]["executive_summary"]
    assert len(body["source_context_hash"]) == 64

    assert client.get(f"/incidents/{incident_id}/narrative").status_code == 200
