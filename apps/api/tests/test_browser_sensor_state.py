# Purpose: verify the browser sensor state machine and destination/exposure enums.
from __future__ import annotations

import pytest

from app.models.domain.browser_sensor import (
    InvalidSensorTransitionError,
    SensorStatus,
    assert_transition,
    can_transition,
)


def test_legal_transitions() -> None:
    assert can_transition(SensorStatus.PENDING, SensorStatus.ACTIVE)
    assert can_transition(SensorStatus.ACTIVE, SensorStatus.DISABLED)
    assert can_transition(SensorStatus.DISABLED, SensorStatus.ACTIVE)
    assert can_transition(SensorStatus.ACTIVE, SensorStatus.REVOKED)
    assert can_transition(SensorStatus.DISABLED, SensorStatus.REVOKED)


def test_revoked_is_terminal() -> None:
    for target in SensorStatus:
        assert not can_transition(SensorStatus.REVOKED, target)
    with pytest.raises(InvalidSensorTransitionError):
        assert_transition(SensorStatus.REVOKED, SensorStatus.ACTIVE)


def test_illegal_transitions_rejected() -> None:
    # Cannot jump from pending straight to disabled, or re-activate a revoked sensor.
    assert not can_transition(SensorStatus.PENDING, SensorStatus.DISABLED)
    with pytest.raises(InvalidSensorTransitionError):
        assert_transition(SensorStatus.PENDING, SensorStatus.DISABLED)
