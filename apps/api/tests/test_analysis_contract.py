# Purpose: validate the RepositorySignals / AnalysisPreviewRequest contract — bounds, optional
#   fields, unknown-field policy, malformed types, and that unsafe fields are ignored, not executed.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.analysis import AnalysisOptions, AnalysisPreviewRequest
from app.models.domain.analysis_signals import (
    MAX_COLLECTION,
    MAX_STRING,
    RepositorySignals,
)


def test_empty_signals_valid() -> None:
    s = RepositorySignals.model_validate({})
    assert s.languages == ()
    assert s.naming_patterns is None


def test_minimal_and_optional_fields() -> None:
    s = RepositorySignals.model_validate({"languages": [{"name": "Python"}]})
    assert s.languages[0].name == "Python"
    assert s.languages[0].confidence is None  # optional


def test_unknown_top_level_field_retained_for_reporting() -> None:
    # extra="allow" on the top level so the endpoint can REPORT ignored keys; never executed.
    s = RepositorySignals.model_validate({"languages": [], "totally_unknown": {"x": 1}})
    assert "totally_unknown" in (s.model_extra or {})


def test_unknown_nested_field_dropped_silently() -> None:
    s = RepositorySignals.model_validate({"languages": [{"name": "Go", "exec": "rm -rf /"}]})
    assert not getattr(s.languages[0], "model_extra", None)


def test_excessive_string_length_rejected() -> None:
    with pytest.raises(ValidationError):
        RepositorySignals.model_validate({"languages": [{"name": "x" * (MAX_STRING + 1)}]})


def test_excessive_collection_size_rejected() -> None:
    with pytest.raises(ValidationError):
        RepositorySignals.model_validate(
            {"languages": [{"name": f"l{i}"} for i in range(MAX_COLLECTION + 1)]}
        )


def test_wrong_type_rejected() -> None:
    with pytest.raises(ValidationError):
        RepositorySignals.model_validate({"languages": "not-a-list"})


def test_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        RepositorySignals.model_validate({"languages": [{"name": "Go", "confidence": 2.0}]})


def test_options_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        AnalysisOptions.model_validate({"maximum_recommendations": 5, "engine": "os.system"})


def test_options_bounds() -> None:
    with pytest.raises(ValidationError):
        AnalysisOptions.model_validate({"maximum_recommendations": 999})
    ok = AnalysisOptions.model_validate({"maximum_recommendations": 5, "minimum_confidence": 0.5})
    assert ok.maximum_recommendations == 5


def test_request_rejects_unknown_top_level_keys() -> None:
    with pytest.raises(ValidationError):
        AnalysisPreviewRequest.model_validate({"signals": {}, "danger": "eval"})


def test_request_scenario_id_bounded() -> None:
    with pytest.raises(ValidationError):
        AnalysisPreviewRequest.model_validate({"signals": {}, "scenario_id": "x" * 65})
