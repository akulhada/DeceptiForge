# Purpose: orchestrate GPT incident-narrative generation with a deterministic fallback.
# Responsibilities: build sanitized context, call the model client when configured, validate its
#   output, and always return a narrative — falling back deterministically on missing config,
#   model error, or invalid output. It never overrides deterministic incident fields.
# Dependencies: settings, the narrative models, context builder, prompt, client, and fallback.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.config.settings import Settings
from app.models.domain.narrative import (
    IncidentNarrative,
    IncidentNarrativeBody,
    IncidentNarrativeContext,
    NarrativeSource,
    NarrativeStatus,
    TokenUsage,
)
from app.models.domain.operations import ReconstructedIncident
from app.prompts.incident_narrative import (
    OUTPUT_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    render_user_prompt,
)
from app.services.incident_narrative.client import NarrativeModelClient, OpenAINarrativeClient
from app.services.incident_narrative.context import NarrativeContextBuilder, context_hash
from app.services.incident_narrative.fallback import fallback_body


class IncidentNarrativeGenerator:
    """Produces an IncidentNarrative from a deterministic incident, model-assisted or fallback."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: NarrativeModelClient | None = None,
        builder: NarrativeContextBuilder | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._builder = builder or NarrativeContextBuilder()
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(self, incident: ReconstructedIncident, organization_id: UUID) -> IncidentNarrative:
        context = self._builder.build(incident)
        digest = context_hash(context)
        client = self._resolve_client()

        if client is None:
            return self._envelope(
                incident,
                context,
                digest,
                fallback_body(context),
                organization_id,
                NarrativeSource.FALLBACK,
                NarrativeStatus.FALLBACK_DISABLED,
            )

        try:
            result = client.complete(
                system=SYSTEM_PROMPT,
                user=render_user_prompt(context),
                schema=OUTPUT_SCHEMA,
                model=self._settings.openai_incident_model,
            )
        except Exception as error:  # any client/SDK failure degrades to fallback
            return self._envelope(
                incident,
                context,
                digest,
                fallback_body(context),
                organization_id,
                NarrativeSource.FALLBACK,
                NarrativeStatus.FALLBACK_ERROR,
                error=f"model request failed ({type(error).__name__})",
            )

        try:
            body = IncidentNarrativeBody.model_validate_json(result.json_text)
        except Exception:
            return self._envelope(
                incident,
                context,
                digest,
                fallback_body(context),
                organization_id,
                NarrativeSource.FALLBACK,
                NarrativeStatus.FALLBACK_INVALID,
                error="model output failed schema validation",
            )

        return self._envelope(
            incident,
            context,
            digest,
            body,
            organization_id,
            NarrativeSource.MODEL,
            NarrativeStatus.GENERATED,
            model=result.model,
            token_usage=result.token_usage,
        )

    def _resolve_client(self) -> NarrativeModelClient | None:
        if self._client is not None:
            return self._client
        if not self._settings.openai_configured or self._settings.openai_api_key is None:
            return None
        return OpenAINarrativeClient(self._settings.openai_api_key)

    def _envelope(
        self,
        incident: ReconstructedIncident,
        context: IncidentNarrativeContext,
        digest: str,
        body: IncidentNarrativeBody,
        organization_id: UUID,
        source: NarrativeSource,
        status: NarrativeStatus,
        *,
        model: str | None = None,
        token_usage: TokenUsage | None = None,
        error: str | None = None,
    ) -> IncidentNarrative:
        return IncidentNarrative(
            narrative_id=self._narrative_id(incident.incident_id, digest),
            incident_id=incident.incident_id,
            organization_id=organization_id,
            source=source,
            status=status,
            model=model,
            prompt_version=PROMPT_VERSION,
            source_context_hash=digest,
            created_at=self._clock(),
            body=body,
            token_usage=token_usage,
            error=error,
        )

    @staticmethod
    def _narrative_id(incident_id: UUID, digest: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"{incident_id}:{digest}")
