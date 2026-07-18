"""Optional GPT incident-narrative layer over deterministic reconstruction.

The generator builds a sanitized, bounded context, calls an optional model client, and always
returns a narrative — falling back deterministically when OpenAI is absent, failing, or invalid.
"""

from app.services.incident_narrative.client import (
    ModelResult,
    NarrativeModelClient,
    OpenAINarrativeClient,
)
from app.services.incident_narrative.context import NarrativeContextBuilder, context_hash
from app.services.incident_narrative.fallback import fallback_body
from app.services.incident_narrative.generator import IncidentNarrativeGenerator
from app.services.incident_narrative.service import NarrativeService

__all__ = [
    "IncidentNarrativeGenerator",
    "ModelResult",
    "NarrativeContextBuilder",
    "NarrativeModelClient",
    "NarrativeService",
    "OpenAINarrativeClient",
    "context_hash",
    "fallback_body",
]
