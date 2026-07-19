# Purpose: verify the AI tripwire state machine, surface mapping, and scope/role wiring.
from __future__ import annotations

import pytest

from app.models.domain.ai_tripwire import (
    AiEventType,
    AiTripwireStatus,
    InvalidAiTransitionError,
    SurfaceType,
    assert_transition,
    can_transition,
    event_surface,
)
from app.services.api_keys import ROLE_SCOPES

S = AiTripwireStatus


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.DRAFT, S.AWAITING_APPROVAL),
        (S.AWAITING_APPROVAL, S.APPROVED),
        (S.AWAITING_APPROVAL, S.REJECTED),
        (S.APPROVED, S.DEPLOYING),
        (S.DEPLOYING, S.DEPLOYED),
        (S.DEPLOYING, S.VERIFICATION_FAILED),
        (S.DEPLOYED, S.RETIRING),
        (S.DEPLOYED, S.DRIFT_DETECTED),
        (S.RETIRING, S.RETIRED),
        (S.FAILED, S.AWAITING_APPROVAL),
        (S.DRIFT_DETECTED, S.RETIRING),
    ],
)
def test_allowed(current: AiTripwireStatus, target: AiTripwireStatus) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.REJECTED, S.DEPLOYING),
        (S.DRAFT, S.DEPLOYED),
        (S.RETIRED, S.DEPLOYING),
        (S.FAILED, S.DEPLOYED),
        (S.AWAITING_APPROVAL, S.DEPLOYING),
        (S.DEPLOYED, S.DEPLOYED),
    ],
)
def test_forbidden(current: AiTripwireStatus, target: AiTripwireStatus) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidAiTransitionError):
        assert_transition(current, target)


def test_terminal_states() -> None:
    for terminal in (S.REJECTED, S.CANCELLED, S.RETIRED):
        assert all(not can_transition(terminal, other) for other in AiTripwireStatus)


def test_event_surface_mapping() -> None:
    assert event_surface(AiEventType.DOCUMENT_RETRIEVED) is SurfaceType.RAG_DOCUMENT
    assert event_surface(AiEventType.TRACE_IN_ANSWER) is SurfaceType.RAG_DOCUMENT
    assert event_surface(AiEventType.RESOURCE_READ) is SurfaceType.MCP_RESOURCE
    assert event_surface(AiEventType.AGENT_TOUCHED) is SurfaceType.MCP_RESOURCE


def test_role_scopes() -> None:
    assert "ai_tripwires:read" in ROLE_SCOPES["viewer"]
    assert "ai_tripwires:create" not in ROLE_SCOPES["viewer"]
    assert "ai_tripwires:create" in ROLE_SCOPES["analyst"]
    assert "ai_tripwires:approve" not in ROLE_SCOPES["analyst"]
    assert "ai_tripwires:ingest" in ROLE_SCOPES["service"]
    assert "ai_tripwires:deploy" in ROLE_SCOPES["service"]
    assert "ai_tripwires:approve" not in ROLE_SCOPES["service"]
    for scope in ("ai_tripwire_connectors:manage", "ai_tripwires:approve", "ai_tripwires:retire"):
        assert scope in ROLE_SCOPES["owner"] and scope in ROLE_SCOPES["admin"]
