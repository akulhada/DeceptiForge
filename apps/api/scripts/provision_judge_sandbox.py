# Purpose: provision judge sandboxes and demo credentials out-of-band.
# Why a script and not an endpoint: judge access must be server-verified with no anonymous fallback.
#   `judge` is absent from TENANT_GRANTABLE_ROLES, so no tenant administrator can mint one, and
#   exposing a public "give me a sandbox" route would be exactly the anonymous fallback the design
#   forbids. An operator runs this and hands the resulting key to a judge over a trusted channel.
#
# Usage (inside the API image or a configured checkout):
#   python scripts/provision_judge_sandbox.py [--ttl-hours 8]
#   python scripts/provision_judge_sandbox.py --demo-credential [--ttl-hours 24]
#
# `--demo-credential` mints a minimal `demo` key bound to the demo organization. The curated demo
# routes MUTATE, so once they are hosted they cannot be left unauthenticated; this is the credential
# that opens them. It carries no tenant writes, no administration and no judge scopes.
#
# The plaintext API key is printed ONCE and is not recoverable afterwards. Treat this output, and
# any log that captures it, as a credential.
from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.services.judge_sandbox import DEFAULT_SANDBOX_TTL_HOURS, JudgeSandboxService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision a judge sandbox session.")
    parser.add_argument(
        "--ttl-hours",
        type=int,
        default=None,
        help=(
            "session lifetime in hours "
            f"(default: JUDGE_SANDBOX_TTL_HOURS or {DEFAULT_SANDBOX_TTL_HOURS})"
        ),
    )
    parser.add_argument(
        "--demo-credential",
        action="store_true",
        help="mint a demo-role key bound to the demo organization instead of a judge sandbox",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.demo_credential:
        return _provision_demo(settings, args.ttl_hours)
    if not settings.allows_judge_workspace:
        # Refuse loudly rather than creating an organization and a credential that no route serves.
        print(
            f"refusing to provision: APP_ENV={settings.app_env} does not host the judge workspace",
            file=sys.stderr,
        )
        return 2
    if not settings.judge_workspace_enabled:
        print(
            "refusing to provision: JUDGE_WORKSPACE_ENABLED is false, so the routes are unmounted",
            file=sys.stderr,
        )
        return 2

    ttl_hours = args.ttl_hours or settings.judge_sandbox_ttl_hours
    engine = create_engine(str(settings.database_url))
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        provisioned = JudgeSandboxService(session, settings).provision(ttl_hours=ttl_hours)
        session.commit()
    finally:
        session.close()

    for line in (
        f"JUDGE_ORG_ID={provisioned.namespace.organization_id}",
        f"JUDGE_SESSION_ID={provisioned.namespace.session_id}",
        f"JUDGE_API_KEY={provisioned.api_key}",
        f"JUDGE_EXPIRES_AT={provisioned.expires_at.isoformat()}",
    ):
        print(line)
    return 0


def _provision_demo(settings: object, ttl_hours: int | None) -> int:
    """Mint a `demo` key bound to the demo organization."""
    from datetime import UTC, datetime, timedelta

    from app.config.constants import DEMO_ORGANIZATION_ID
    from app.services.api_keys import ApiKeyService

    if not settings.allows_demo_surface:  # type: ignore[attr-defined]
        print(
            f"refusing to provision: APP_ENV={settings.app_env} does not host the demo",  # type: ignore[attr-defined]
            file=sys.stderr,
        )
        return 2
    if not settings.demo_enabled:  # type: ignore[attr-defined]
        print(
            "refusing to provision: DEMO_ENABLED is false, so the demo routes are unmounted",
            file=sys.stderr,
        )
        return 2

    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours or 24)
    engine = create_engine(str(settings.database_url))  # type: ignore[attr-defined]
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        # issuer_scopes is None: out-of-band provisioning, not a tenant administrator minting a key.
        # `demo` is absent from TENANT_GRANTABLE_ROLES, so this is the only path that creates one.
        _, plaintext = ApiKeyService(session).create(
            DEMO_ORGANIZATION_ID, "demo-story", "demo", expires_at=expires_at
        )
        session.commit()
    finally:
        session.close()

    print(f"DEMO_ORG_ID={DEMO_ORGANIZATION_ID}")
    print(f"DEMO_API_KEY={plaintext}")
    print(f"DEMO_EXPIRES_AT={expires_at.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
