# Purpose: the `deceptiforge-agent` CLI wrapper (start / event / finish).
# Responsibilities: provide a thin command-line interface that starts a scoped session, emits a
#   single minimized activity event, or finishes a session, signing each request with the sensor
#   secret. It observes/receives events; it never executes the agent and never sends file content.
#   Run as: python -m app.agent_sdk.cli <start|event|finish> ...
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from app.agent_sdk.adapter import AdapterError, JsonlAdapter, LocalFsAdapter
from app.agent_sdk.client import AgentClient, AgentClientConfig


def _urllib_transport(
    method: str, path: str, body: bytes, headers: dict[str, str]
) -> tuple[int, dict[str, Any]]:
    base = os.environ.get("DECEPTIFORGE_URL", "http://localhost:8000")
    req = urllib.request.Request(f"{base}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed base URL
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, {}
    except Exception:  # noqa: BLE001 - offline path is handled by the caller's queue
        return 0, {}


def _config() -> AgentClientConfig:
    def env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            print(f"missing environment variable {name}", file=sys.stderr)
            raise SystemExit(2)
        return value

    return AgentClientConfig(
        base_url=os.environ.get("DECEPTIFORGE_URL", "http://localhost:8000"),
        organization_id=env("DECEPTIFORGE_ORG_ID"),
        api_key=env("DECEPTIFORGE_API_KEY"),
        sensor_public_id=env("DECEPTIFORGE_SENSOR_ID"),
        signing_secret=env("DECEPTIFORGE_SENSOR_SECRET"),
    )


def _adapter(name: str) -> JsonlAdapter:
    return LocalFsAdapter() if name == "local_fs" else JsonlAdapter()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deceptiforge-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="start a scoped agent session")
    p_start.add_argument("--session-id", required=True)
    p_start.add_argument("--agent-type", required=True)
    p_start.add_argument("--task", default="")
    p_start.add_argument("--allow", action="append", default=[])
    p_start.add_argument("--deny", action="append", default=[])

    p_event = sub.add_parser("event", help="emit one minimized activity event (JSON on stdin)")
    p_event.add_argument("--session-id", required=True)
    p_event.add_argument("--adapter", default="jsonl", choices=["jsonl", "local_fs"])

    p_finish = sub.add_parser("finish", help="finish a session (drain the queue)")
    p_finish.add_argument("--session-id", required=True)
    p_finish.add_argument("--status", default="completed")

    args = parser.parse_args(argv)
    client = AgentClient(_config(), _urllib_transport)

    if args.command == "start":
        status, _ = client.start_session(
            external_session_id=args.session_id, agent_type=args.agent_type,
            task_summary=args.task, allowed_paths=tuple(args.allow), denied_paths=tuple(args.deny),
        )
        print(json.dumps({"status": status}))
        return 0 if 200 <= status < 300 else 1

    if args.command == "event":
        client._session_external_id = args.session_id  # noqa: SLF001 - CLI binds the session
        raw = json.loads(sys.stdin.read() or "{}")
        try:
            event = _adapter(args.adapter).normalize_event(raw)
        except AdapterError as error:
            print(f"rejected: {error}", file=sys.stderr)
            return 2
        status, resp = client.emit_event(event)
        print(json.dumps({"status": status, "response": resp, "queued": client.queue_size}))
        return 0

    # finish
    client._session_external_id = args.session_id  # noqa: SLF001
    status, resp = client.finish(status=args.status)
    print(json.dumps({"status": status, "response": resp}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
