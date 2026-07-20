# Purpose: verify the agent sensor state machine, destructive-event flag, and sensitive path set.
from __future__ import annotations

import pytest

from app.models.domain.agent_sensor import (
    SENSITIVE_CLASSES,
    AgentEventType,
    AgentSensorStatus,
    InvalidSensorTransitionError,
    PathClass,
    assert_transition,
    can_transition,
    is_destructive,
)


def test_sensor_transitions() -> None:
    assert can_transition(AgentSensorStatus.PENDING, AgentSensorStatus.ACTIVE)
    assert can_transition(AgentSensorStatus.ACTIVE, AgentSensorStatus.DISABLED)
    assert can_transition(AgentSensorStatus.DISABLED, AgentSensorStatus.ACTIVE)
    assert can_transition(AgentSensorStatus.ACTIVE, AgentSensorStatus.REVOKED)


def test_revoked_is_terminal() -> None:
    for target in AgentSensorStatus:
        assert not can_transition(AgentSensorStatus.REVOKED, target)
    with pytest.raises(InvalidSensorTransitionError):
        assert_transition(AgentSensorStatus.REVOKED, AgentSensorStatus.ACTIVE)


def test_illegal_transition_rejected() -> None:
    assert not can_transition(AgentSensorStatus.PENDING, AgentSensorStatus.DISABLED)
    with pytest.raises(InvalidSensorTransitionError):
        assert_transition(AgentSensorStatus.PENDING, AgentSensorStatus.DISABLED)


def test_destructive_events() -> None:
    assert is_destructive(AgentEventType.FILE_DELETED)
    assert is_destructive(AgentEventType.DENIED_ACTION_ATTEMPTED)
    assert not is_destructive(AgentEventType.FILE_READ)


def test_sensitive_classes() -> None:
    assert PathClass.CREDENTIAL in SENSITIVE_CLASSES
    assert PathClass.AUTHENTICATION in SENSITIVE_CLASSES
    assert PathClass.TASK_RELEVANT not in SENSITIVE_CLASSES
