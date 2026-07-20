# Purpose: minimal signing client for the agent wrapper/CLI.
# Responsibilities: start a scoped session, emit signed minimized activity events, and finish the
#   session — signing each request (monitor-signature-v1) with the sensor secret, retrying safely,
#   and holding a bounded offline queue that never contains file content. The transport is injected
#   so it is testable without real network. Does not execute the agent.
from __future__ import annotations

import json
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent_sdk.adapter import NormalizedEvent
from app.services.monitor_signing import canonical_request, sign

# transport(method, path, body_bytes, headers) -> (status_code, response_json)
Transport = Callable[[str, str, bytes, dict[str, str]], tuple[int, dict[str, Any]]]


@dataclass(frozen=True)
class AgentClientConfig:
    base_url: str
    organization_id: str
    api_key: str
    sensor_public_id: str
    signing_secret: str
    queue_limit: int = 500


class AgentClient:
    def __init__(self, config: AgentClientConfig, transport: Transport) -> None:
        self._c = config
        self._transport = transport
        self._session_external_id: str | None = None
        self._queue: deque[dict[str, Any]] = deque(maxlen=config.queue_limit)
        self._queued_ids: set[str] = set()

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def _signed_headers(self, path: str, body: bytes) -> dict[str, str]:
        nonce = secrets.token_hex(16)
        timestamp = str(time.time())
        canonical = canonical_request(
            method="POST", path=path, organization_id=self._c.organization_id,
            monitor_id=self._c.sensor_public_id, timestamp=timestamp, nonce=nonce, body=body,
        )
        return {
            "content-type": "application/json",
            "X-DeceptiForge-Org-Id": self._c.organization_id,
            "X-DeceptiForge-API-Key": self._c.api_key,
            "X-DeceptiForge-Sensor-Id": self._c.sensor_public_id,
            "X-DeceptiForge-Nonce": nonce,
            "X-DeceptiForge-Timestamp": timestamp,
            "X-DeceptiForge-Signature": sign(self._c.signing_secret, canonical),
        }

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        headers = self._signed_headers(path, body)
        return self._transport("POST", path, body, headers)

    def start_session(
        self, *, external_session_id: str, agent_type: str, task_summary: str,
        allowed_paths: tuple[str, ...] = (), denied_paths: tuple[str, ...] = (),
    ) -> tuple[int, dict[str, Any]]:
        self._session_external_id = external_session_id
        return self._safe_post(
            "/agent-sessions",
            {
                "external_session_id": external_session_id, "agent_type": agent_type,
                "task_summary": task_summary, "allowed_paths": list(allowed_paths),
                "denied_paths": list(denied_paths),
            },
        )

    def emit_event(self, event: NormalizedEvent) -> tuple[int, dict[str, Any]]:
        if self._session_external_id is None:
            raise RuntimeError("start_session must be called before emit_event")
        payload = event.to_body(self._session_external_id)
        self._flush()  # opportunistically drain the queue first
        status, resp = self._safe_post("/monitoring/agent-events", payload)
        if not _delivered(status):
            self._enqueue(payload)
        return status, resp

    def finish(self, *, status: str = "completed") -> tuple[int, dict[str, Any]]:
        if self._session_external_id is None:
            raise RuntimeError("no active session")
        self._flush()
        # The complete endpoint is keyed by internal session id in the API; the wrapper resolves it
        # by listing, but for the CLI path we simply drain the queue. Completion is best-effort.
        return 200, {"queued": self.queue_size}

    def _safe_post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            return self._post(path, payload)
        except Exception:  # noqa: BLE001 - offline/transport failure must not crash the agent
            return 0, {}

    def _enqueue(self, payload: dict[str, Any]) -> None:
        eid = str(payload.get("external_event_id"))
        if eid in self._queued_ids:
            return  # dedupe -> a retry never double-reports
        if len(self._queue) == self._queue.maxlen:
            dropped = self._queue.popleft()
            self._queued_ids.discard(str(dropped.get("external_event_id")))
        self._queue.append(payload)
        self._queued_ids.add(eid)

    def _flush(self) -> None:
        for _ in range(len(self._queue)):
            payload = self._queue[0]
            status, _resp = self._safe_post("/monitoring/agent-events", payload)
            if _delivered(status):
                self._queue.popleft()
                self._queued_ids.discard(str(payload.get("external_event_id")))
            else:
                break  # still offline; stop, retry later


def _delivered(status: int) -> bool:
    # 2xx accepted; 409 = duplicate/replay already recorded -> treat as delivered.
    return 200 <= status < 300 or status == 409
