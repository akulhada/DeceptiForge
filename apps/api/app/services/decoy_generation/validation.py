"""Validation and collision checks shared by all deterministic payloads."""

import json

from app.models.domain.decoy import (
    CollisionCheckMetadata,
    DecoySafetyMetadata,
    DecoyValidationResult,
    GeneratedDatabaseRecord,
    GeneratedDocument,
    GeneratedSecret,
)
from app.models.domain.intelligence import OrganizationContextProfile, PlacementRecommendation
from app.services.decoy_generation.templates import DecoyTemplate


class DecoyValidationPipeline:
    def validate(
        self,
        payload: GeneratedSecret | GeneratedDocument | GeneratedDatabaseRecord,
        recommendation: PlacementRecommendation,
        template: DecoyTemplate,
        context: OrganizationContextProfile,
        reserved_names: tuple[str, ...],
    ) -> tuple[DecoyValidationResult, CollisionCheckMetadata]:
        reasons: list[str] = []
        checks = [
            "schema",
            "placement_compatibility",
            "naming",
            "safety",
            "traceability",
            "serialization",
        ]
        if recommendation.target_type not in template.target_types:
            reasons.append("placement target is not supported by the selected template")
        payload_values = payload.model_dump(mode="json")
        if any(field not in payload_values for field in template.required_fields):
            reasons.append("template required fields are missing")
        observed = self._observed_names(context, reserved_names)
        candidate_names = self._candidate_names(payload)
        collision_reasons = tuple(name for name in candidate_names if name.lower() in observed)
        collision = CollisionCheckMetadata(
            checked_names=tuple(sorted(observed)),
            collision_detected=bool(collision_reasons),
            reasons=collision_reasons,
        )
        if collision.collision_detected:
            reasons.append("generated name collides with an observed or reserved name")
        if isinstance(payload, GeneratedSecret) and not payload.fake_value.startswith("dfg_inert_"):
            reasons.append("secret payload is not inert")
        if isinstance(payload, GeneratedDatabaseRecord) and "@invalid.example" not in str(payload):
            reasons.append("database payload lacks the synthetic-contact safeguard")
        try:
            json.dumps(payload_values)
        except (TypeError, ValueError):
            reasons.append("payload is not JSON serializable")
        return (
            DecoyValidationResult(valid=not reasons, checks=tuple(checks), reasons=tuple(reasons)),
            collision,
        )

    @staticmethod
    def safety_metadata() -> DecoySafetyMetadata:
        return DecoySafetyMetadata()

    @staticmethod
    def _candidate_names(
        payload: GeneratedSecret | GeneratedDocument | GeneratedDatabaseRecord,
    ) -> tuple[str, ...]:
        if isinstance(payload, GeneratedSecret):
            return (payload.key_name,)
        if isinstance(payload, GeneratedDocument):
            return (payload.title,)
        return (payload.table_name,)

    @staticmethod
    def _observed_names(
        context: OrganizationContextProfile, reserved_names: tuple[str, ...]
    ) -> set[str]:
        naming = context.naming_profile
        samples = (
            ()
            if naming is None
            else tuple(
                sample for convention in naming.naming_style for sample in convention.samples
            )
        )
        return {name.lower() for name in (*samples, *reserved_names)}
