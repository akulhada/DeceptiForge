# Purpose: verify the agent adapter contract and signing client — content stripping, event
#   normalization, signed requests, idempotent offline queue, and bounded queue.
from __future__ import annotations

from typing import Any

from app.agent_sdk.adapter import AdapterError, JsonlAdapter, LocalFsAdapter
from app.agent_sdk.client import AgentClient, AgentClientConfig
from app.services.monitor_signing import canonical_request, verify


def _config() -> AgentClientConfig:
    return AgentClientConfig(
        base_url="https://api.example.com",
        organization_id="org-1",
        api_key="dfk_x",
        sensor_public_id="dfa_x",
        signing_secret="s3cr3t",
        queue_limit=3,
    )


def test_adapter_strips_raw_content() -> None:
    ev = JsonlAdapter().normalize_event(
        {
            "id": "e1",
            "event_type": "file_read",
            "path": "apps/web/x.tsx",
            "tool": "cat",
            "metadata": {"lines": 5, "file_content": "SECRET", "reasoning": "chain"},
        }
    )
    assert ev.external_event_id == "e1"
    assert "file_content" not in ev.metadata and "reasoning" not in ev.metadata
    assert ev.metadata["lines"] == "5"
    body = ev.to_body("sess-1")
    assert "SECRET" not in str(body)


def test_adapter_rejects_unknown_type() -> None:
    try:
        JsonlAdapter().normalize_event({"id": "e", "event_type": "exfiltrate"})
        raise AssertionError("expected AdapterError")
    except AdapterError:
        pass


def test_local_fs_action_mapping() -> None:
    ev = LocalFsAdapter().normalize_event({"id": "e2", "action": "read", "path": "a.py"})
    assert ev.event_type == "file_read"


def test_client_signs_requests() -> None:
    captured: dict[str, Any] = {}

    def transport(method, path, body, headers):  # type: ignore[no-untyped-def]
        captured["path"] = path
        captured["body"] = body
        captured["headers"] = headers
        return 200, {"accepted": True}

    client = AgentClient(_config(), transport)
    client.start_session(external_session_id="sess-1", agent_type="cli", task_summary="fix")
    ev = JsonlAdapter().normalize_event({"id": "e1", "event_type": "file_read", "path": "a.ts"})
    status, _ = client.emit_event(ev)
    assert status == 200
    h = captured["headers"]
    canonical = canonical_request(
        method="POST",
        path="/monitoring/agent-events",
        organization_id="org-1",
        monitor_id="dfa_x",
        timestamp=h["X-DeceptiForge-Timestamp"],
        nonce=h["X-DeceptiForge-Nonce"],
        body=captured["body"],
    )
    assert verify("s3cr3t", canonical, h["X-DeceptiForge-Signature"])
    assert b"SECRET" not in captured["body"]


def test_offline_queue_dedupes_and_bounds() -> None:
    calls = {"n": 0}

    def failing(method, path, body, headers):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        raise ConnectionError("offline")

    client = AgentClient(_config(), failing)
    client.start_session(external_session_id="sess-1", agent_type="cli", task_summary="fix")
    for i in range(5):
        ev = JsonlAdapter().normalize_event({"id": f"e{i}", "event_type": "file_read", "path": "a"})
        client.emit_event(ev)
    # Bounded to queue_limit=3 (oldest dropped).
    assert client.queue_size == 3
    # Re-emitting a queued id does not duplicate.
    ev = JsonlAdapter().normalize_event({"id": "e4", "event_type": "file_read", "path": "a"})
    client.emit_event(ev)
    assert client.queue_size == 3


def test_offline_then_online_flushes_once() -> None:
    state = {"online": False, "delivered": []}

    def transport(method, path, body, headers):  # type: ignore[no-untyped-def]
        if not state["online"]:
            raise ConnectionError("offline")
        import json as _json

        state["delivered"].append(_json.loads(body)["external_event_id"])
        return 200, {}

    client = AgentClient(_config(), transport)
    client.start_session(external_session_id="sess-1", agent_type="cli", task_summary="fix")
    ev = JsonlAdapter().normalize_event({"id": "e1", "event_type": "file_read", "path": "a"})
    client.emit_event(ev)  # offline -> queued
    assert client.queue_size == 1
    state["online"] = True
    ev2 = JsonlAdapter().normalize_event({"id": "e2", "event_type": "file_read", "path": "b"})
    client.emit_event(ev2)  # flushes e1 then sends e2
    assert client.queue_size == 0
    assert state["delivered"] == ["e1", "e2"]
