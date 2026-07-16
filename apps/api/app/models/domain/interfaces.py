# Purpose: declare core engine and monitor interfaces. Responsibilities: define dependency boundaries without implementations, prompts, monitoring code, or routing. Future modules: implement these protocols in infrastructure adapters and application services.
from __future__ import annotations

from typing import Protocol

from app.models.domain.decoy import Believability, Decoy, Placement
from app.models.domain.operations import Alert, Coverage, Incident, TimelineEvent
from app.models.domain.organization import Repository, RepositoryProfile


class RepositoryScanner(Protocol):
    """Produces a repository profile from one repository source."""

    async def scan(self, repository: Repository) -> RepositoryProfile: ...


class ProfileGenerator(Protocol):
    """Produces an immutable profile snapshot from repository context."""

    async def generate(self, repository: Repository) -> RepositoryProfile: ...


class DecoyGenerator(Protocol):
    """Produces a typed decoy envelope from a repository profile."""

    async def generate(self, profile: RepositoryProfile) -> Decoy: ...


class PlacementEngine(Protocol):
    """Produces a placement assessment for one decoy."""

    async def assess(self, decoy: Decoy, profile: RepositoryProfile) -> Placement: ...


class BelievabilityEngine(Protocol):
    """Produces an explainable quality assessment for one decoy."""

    async def assess(self, decoy: Decoy, placement: Placement) -> Believability: ...


class MonitoringEngine(Protocol):
    """Normalizes a timeline event into an optional alert."""

    async def evaluate(self, event: TimelineEvent) -> Alert | None: ...


class IncidentEngine(Protocol):
    """Builds an incident assessment from normalized alerts."""

    async def assess(self, alerts: tuple[Alert, ...]) -> Incident | None: ...


class CoverageEngine(Protocol):
    """Measures coverage for one repository context."""

    async def measure(self, profile: RepositoryProfile) -> Coverage: ...


class PromptEngine(Protocol):
    """Resolves a versioned prompt reference without defining prompt content."""

    async def resolve(self, prompt_name: str, version: str) -> str: ...


class BrowserMonitor(Protocol):
    """Normalizes browser activity into a timeline event."""

    async def observe(self, payload: bytes) -> TimelineEvent | None: ...


class DatabaseMonitor(Protocol):
    """Normalizes database audit material into a timeline event."""

    async def observe(self, payload: bytes) -> TimelineEvent | None: ...
