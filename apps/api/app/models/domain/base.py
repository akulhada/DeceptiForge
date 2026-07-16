# Purpose: define strict domain-model primitives. Responsibilities: provide typed identifiers, immutable validation, and JSON/database/event serialization. Future modules: add only cross-domain primitives that are stable across transports.
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, NewType
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OrganizationId = NewType("OrganizationId", UUID)
RepositoryId = NewType("RepositoryId", UUID)
RepositoryProfileId = NewType("RepositoryProfileId", UUID)

JsonObject = dict[str, Any]


class DomainModel(BaseModel):
    """Immutable, strict model with transport-neutral serialization.

    Purpose: make the domain contract safe at API, database, and event boundaries.
    Fields: every subclass defines its own stable data fields.
    Relationships: subclasses refer to other aggregates only by typed IDs.
    Future extensibility: add explicit schema revisions rather than silently changing semantics.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def to_api(self) -> JsonObject:
        """Serialize the model using JSON-compatible API values."""
        return self.model_dump(mode="json")

    def to_database(self) -> JsonObject:
        """Serialize the model for a JSON/JSONB persistence column."""
        return self.model_dump(mode="json")

    def to_event(self, *, event_type: str, occurred_at: datetime) -> JsonObject:
        """Serialize a versioned envelope suitable for a future event stream."""
        return {
            "event_type": event_type,
            "occurred_at": occurred_at.isoformat(),
            "schema_version": 1,
            "payload": self.to_api(),
        }

    @classmethod
    def from_database(cls, record: JsonObject) -> "DomainModel":
        """Reconstruct from JSON/JSONB values while preserving strict model rules."""
        return cls.model_validate_json(json.dumps(record))


class RepositoryStatistics(DomainModel):
    """Immutable repository-size snapshot.

    Purpose: retain measurable context for profile confidence and placement decisions.
    Fields: line, file, commit, contributor, and dependency counts.
    Relationships: embedded only in RepositoryProfile; it is not an aggregate.
    Future extensibility: add explicitly named metrics without repurposing existing counts.
    """

    file_count: int = Field(ge=0)
    line_count: int = Field(ge=0)
    commit_count: int = Field(ge=0)
    contributor_count: int = Field(ge=0)
    dependency_count: int = Field(ge=0)
