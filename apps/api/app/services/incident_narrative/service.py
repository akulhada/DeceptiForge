# Purpose: coordinate narrative generation with organization scoping, revisions, and cost control.
# Responsibilities: fetch the incident within its organization, reuse a matching prior narrative
#   under a cooldown, and otherwise append a new revision. It never mutates incident data.
# Dependencies: the artifact repository, settings, and the narrative generator.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.config.settings import Settings
from app.models.domain.narrative import IncidentNarrative, NarrativeSource
from app.repositories.artifacts import ArtifactRepository
from app.services.incident_narrative.context import NarrativeContextBuilder, context_hash
from app.services.incident_narrative.generator import IncidentNarrativeGenerator


class NarrativeService:
    """Organization-scoped narrative use cases with revisioning and a reuse/cooldown guard."""

    def __init__(
        self,
        repository: ArtifactRepository,
        settings: Settings,
        *,
        generator: IncidentNarrativeGenerator | None = None,
        builder: NarrativeContextBuilder | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._generator = generator or IncidentNarrativeGenerator(settings)
        self._builder = builder or NarrativeContextBuilder()
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(
        self, organization_id: UUID, incident_id: UUID, *, force: bool = False
    ) -> IncidentNarrative | None:
        incident = self._repo.get_incident(organization_id, incident_id)
        if incident is None:
            return None

        digest = context_hash(self._builder.build(incident))
        latest = self._repo.latest_narrative(organization_id, incident_id)
        if latest is not None and not force and self._reusable(latest, digest):
            return latest

        narrative = self._generator.generate(incident, organization_id)
        revision = self._repo.next_revision_number(organization_id, incident_id)
        narrative = narrative.model_copy(update={"revision_number": revision})
        self._repo.add_narrative_revision(narrative)
        self._repo.prune_narrative_revisions(
            organization_id, incident_id, self._settings.narrative_revision_retention_count
        )
        return narrative

    def latest(self, organization_id: UUID, incident_id: UUID) -> IncidentNarrative | None:
        return self._repo.latest_narrative(organization_id, incident_id)

    def history(self, organization_id: UUID, incident_id: UUID) -> tuple[IncidentNarrative, ...]:
        return self._repo.list_narratives(organization_id, incident_id)

    def _reusable(self, latest: IncidentNarrative, digest: str) -> bool:
        if latest.source_context_hash != digest:
            return False
        if latest.source is NarrativeSource.MODEL:
            return True  # a successful model narrative for this context is reused, saving cost
        age = (self._clock() - latest.created_at).total_seconds()
        return age < self._settings.narrative_cooldown_seconds
