"""Deterministic safety-oriented context scoring and ranking."""

from app.models.domain.intelligence import ContextArea, ContextConfidence
from app.services.context_engine.classification import ContextClassification
from app.services.context_engine.normalization import NormalizedContext


class ContextScores:
    def __init__(self, context: NormalizedContext, classification: ContextClassification) -> None:
        profile = context.features.profile
        zones: list[ContextArea] = []

        def add(name: str, priority: float, rationale: str, evidence: tuple[str, ...]) -> None:
            zones.append(
                ContextArea(name=name, priority=priority, rationale=rationale, evidence=evidence)
            )

        if profile.secret_locations or context.environment_conventions:
            add(
                "configuration",
                0.95,
                "Secret or environment configuration evidence was found.",
                tuple(location.path for location in profile.secret_locations),
            )
        if profile.databases:
            add(
                "database",
                0.9,
                "Database technology was detected.",
                tuple(item.name for item in profile.databases),
            )
        if profile.services:
            add(
                "services",
                0.8,
                "Service boundaries were detected.",
                tuple(item.name for item in profile.services),
            )
        if profile.mcp_configurations:
            add(
                "mcp",
                0.9,
                "MCP configuration was detected.",
                tuple(item.name for item in profile.mcp_configurations),
            )
        if profile.documentation:
            add(
                "documentation",
                0.65,
                "Documentation assets were detected.",
                tuple(item.name for item in profile.documentation),
            )
        self.zones = tuple(sorted(zones, key=lambda item: (-item.priority, item.name)))
        self.sensitive_assets = tuple(
            item
            for item, present in (
                (
                    "secret_configuration",
                    bool(profile.secret_locations or context.environment_conventions),
                ),
                ("database_record", bool(profile.databases)),
                (
                    "deployment_configuration",
                    bool(
                        profile.infrastructure.docker_files
                        or profile.infrastructure.terraform_files
                    ),
                ),
                ("mcp_configuration", bool(profile.mcp_configurations)),
                ("operational_document", bool(profile.documentation)),
            )
            if present
        )
        self.ai_risk = round(
            min(
                1.0,
                0.25 * bool(profile.mcp_configurations)
                + 0.2 * bool(profile.documentation)
                + 0.2 * bool(profile.services)
                + 0.15 * bool(profile.secret_locations),
            ),
            3,
        )
        self.database_confidence = max((item.confidence for item in profile.databases), default=0.0)
        self.confidence = round(
            min(1.0, (context.features.evidence_count / 10) * (0.75 if profile.truncated else 1.0)),
            3,
        )
        self.metadata = (
            ContextConfidence(
                dimension="repository_signals",
                confidence=self.confidence,
                evidence_count=context.features.evidence_count,
            ),
        )


class ContextScorer:
    def score(
        self, context: NormalizedContext, classification: ContextClassification
    ) -> ContextScores:
        return ContextScores(context, classification)
