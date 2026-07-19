# Purpose: compact factories for decoy assets/plans/reports used by deployment tests.
# Responsibilities: build the smallest valid DecoyAsset / plan / BelievabilitySafetyReport
#   graph so preview/safety/job tests avoid the full generation engine.
from __future__ import annotations

from uuid import UUID, uuid4

from app.models.domain.base import DecoyId
from app.models.domain.decoy import (
    BelievabilityDecision,
    BelievabilityInputs,
    BelievabilitySafetyReport,
    BelievabilityScoreBreakdown,
    CollisionCheckMetadata,
    DecoyAsset,
    DecoyGenerationPlan,
    DecoyKind,
    DecoySafetyMetadata,
    DecoyTemplateId,
    DecoyValidationResult,
    GeneratedDocument,
    RotationMetadata,
    TriggerMetadataPlaceholder,
)


def make_asset(
    target_location: str,
    *,
    decoy_id: UUID | None = None,
    trace: str = "DFG-TRACE",
    collision: bool = False,
) -> DecoyAsset:
    did = DecoyId(decoy_id or uuid4())
    return DecoyAsset(
        decoy_id=did,
        decoy_type=DecoyKind.DOCUMENT,
        target_placement_id=uuid4(),
        target_location=target_location,
        payload=GeneratedDocument(
            title="Runbook",
            body="Synthetic inert runbook body.",
            target_document_type="runbook",
            sensitivity_label="internal",
            trace_identifier=trace,
        ),
        template_id=DecoyTemplateId.DOCUMENT_V1,
        believability_inputs=BelievabilityInputs(
            naming_match=0.9,
            entropy_profile=0.5,
            context_match=0.9,
            placement_match=0.9,
            schema_realism=0.9,
            business_realism=0.9,
            safety_risk=0.1,
        ),
        safety_metadata=DecoySafetyMetadata(),
        collision_check=CollisionCheckMetadata(collision_detected=collision),
        trigger_metadata=TriggerMetadataPlaceholder(trace_identifier=trace),
        rotation_metadata=RotationMetadata(rotation_recommendation="Rotate within 90 days."),
        explanation=("Inert document decoy.",),
        validation=DecoyValidationResult(valid=True),
    )


def make_plan(*assets: DecoyAsset) -> DecoyGenerationPlan:
    return DecoyGenerationPlan(repository_name="payments", assets=tuple(assets))


def make_report(
    decoy_id: UUID, decision: BelievabilityDecision = BelievabilityDecision.ACCEPT
) -> BelievabilitySafetyReport:
    return BelievabilitySafetyReport(
        decoy_id=decoy_id,
        overall_believability_score=90.0,
        overall_safety_score=95.0,
        decision=decision,
        breakdown=BelievabilityScoreBreakdown(
            naming_realism=90,
            context_fit=90,
            placement_compatibility=90,
            schema_completeness=90,
            entropy_realism=90,
            business_realism=90,
            traceability_quality=90,
            safety_inertness=95,
            production_collision_risk=5,
            accidental_use_risk=5,
            obvious_trap_risk=5,
        ),
    )
