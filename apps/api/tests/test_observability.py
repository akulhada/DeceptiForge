# Purpose: verify structured operational metrics are emitted and never carry secrets.
# Responsibilities: confirm rejection/acceptance events are logged on the metrics logger and that
#   forbidden fields (secrets, signatures, nonces, raw evidence) are stripped. Dependencies: the
#   metrics helper and Python logging capture.
from __future__ import annotations

import logging

from app.services.metrics import emit


def test_emit_records_event_on_metrics_logger(caplog) -> None:  # type: ignore[no-untyped-def]
    with caplog.at_level(logging.INFO, logger="deceptiforge.metrics"):
        emit("rate_limit_rejected", endpoint="monitoring:ingest", organization_id="org-1")
    record = next(r for r in caplog.records if r.msg == "rate_limit_rejected")
    assert record.__dict__["event"] == "rate_limit_rejected"
    assert record.__dict__["endpoint"] == "monitoring:ingest"


def test_emit_strips_forbidden_fields(caplog) -> None:  # type: ignore[no-untyped-def]
    with caplog.at_level(logging.INFO, logger="deceptiforge.metrics"):
        emit("monitor_ingest_accepted", organization_id="org-1", signature="abc", nonce="n1")
    record = next(r for r in caplog.records if r.msg == "monitor_ingest_accepted")
    assert "signature" not in record.__dict__
    assert "nonce" not in record.__dict__
    assert record.__dict__["organization_id"] == "org-1"


def test_body_size_rejection_emits_metric(make_client, caplog) -> None:  # type: ignore[no-untyped-def]
    import os

    os.environ["MAX_REQUEST_BODY_BYTES"] = "50"
    try:
        with make_client(demo_enabled=True, app_env="development") as client:
            with caplog.at_level(logging.INFO, logger="deceptiforge.metrics"):
                client.post("/monitoring/events", content=b"x" * 200)
        assert any(r.msg == "body_size_rejected" for r in caplog.records)
    finally:
        os.environ.pop("MAX_REQUEST_BODY_BYTES", None)
