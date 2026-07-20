# Purpose: manage hashed, scoped, organization-bound API keys and authenticate requests.
# Responsibilities: generate keys (plaintext shown once), hash before storage, look up by prefix,
#   verify status/expiry, update last_used_at, and write security-audit rows. Never stores or logs
#   plaintext keys. Dependencies: SQLAlchemy session, records, and the role/scope catalog.
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.records import ApiKeyRecord, SecurityAuditRecord

# ---- roles and permissions -----------------------------------------------------------------------

PERMISSIONS: frozenset[str] = frozenset(
    {
        "repositories:read",
        "repositories:write",
        "placements:read",
        "placements:write",
        "decoys:read",
        "decoys:write",
        "validation:read",
        "validation:write",
        "monitoring:read",
        "monitoring:ingest",
        "alerts:read",
        "alerts:write",
        "incidents:read",
        "incidents:write",
        "narratives:read",
        "narratives:write",
        "demo:run",
        "decoy_deployments:read",
        "decoy_deployments:create",
        "decoy_deployments:approve",
        "decoy_deployments:execute",
        "decoy_deployments:retire",
        "decoy_deployments:rollback",
        "database_connectors:read",
        "database_connectors:manage",
        "database_schema:read",
        "database_honey:read",
        "database_honey:create",
        "database_honey:approve",
        "database_honey:deploy",
        "database_honey:retire",
        "database_honey:rollback",
        "ai_tripwire_connectors:read",
        "ai_tripwire_connectors:manage",
        "ai_tripwires:read",
        "ai_tripwires:create",
        "ai_tripwires:approve",
        "ai_tripwires:deploy",
        "ai_tripwires:retire",
        "ai_tripwires:ingest",
        "browser_sensors:read",
        "browser_sensors:manage",
        "browser_policy:read",
        "browser_policy:manage",
        "browser_events:ingest",
        "browser_events:read",
        "agent_sensors:read",
        "agent_sensors:manage",
        "agent_sessions:read",
        "agent_sessions:create",
        "agent_events:ingest",
        "agent_policies:read",
        "agent_policies:manage",
        "agent_violations:read",
        "coverage:read",
        "coverage:recalculate",
        "coverage:manage_policy",
        "admin:manage_keys",
        "admin:manage_monitors",
        "admin:read_audit",
    }
)

_READS = frozenset(p for p in PERMISSIONS if p.endswith(":read"))

ROLE_SCOPES: dict[str, frozenset[str]] = {
    "owner": PERMISSIONS,
    "admin": PERMISSIONS,
    "analyst": _READS
    | frozenset(
        {
            "narratives:write",
            "incidents:write",
            "alerts:write",
            "demo:run",
            "decoy_deployments:create",
            "database_honey:create",
            "ai_tripwires:create",
            "agent_sessions:create",
        }
    ),
    "viewer": _READS,
    # Service keys execute approved deployment jobs; they cannot create or approve them.
    "service": frozenset(
        {
            "monitoring:read",
            "monitoring:ingest",
            "decoy_deployments:read",
            "decoy_deployments:execute",
            "database_honey:read",
            "database_honey:deploy",
            "ai_tripwires:read",
            "ai_tripwires:deploy",
            "ai_tripwires:ingest",
            "coverage:read",
            "coverage:recalculate",
        }
    ),
    # Browser sensor keys are provisioned per-installation at enrollment. They may fetch their
    # scoped policy/registry and ingest signed paste events — nothing else.
    "browser_sensor": frozenset(
        {
            "browser_policy:read",
            "browser_events:ingest",
        }
    ),
    # Agent sensor keys are provisioned per-install at enrollment. They may start scoped sessions,
    # fetch scope policy, and ingest signed activity events — nothing else.
    "agent_sensor": frozenset(
        {
            "agent_sessions:create",
            "agent_policies:read",
            "agent_events:ingest",
        }
    ),
}


@dataclass(frozen=True)
class AuthContext:
    organization_id: UUID
    scopes: frozenset[str]
    role: str
    key_id: UUID | None


class AuthError(Exception):
    """Raised when authentication fails; carries an HTTP status and safe message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, hash). Plaintext must be shown to the caller only once."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    plaintext = f"dfk_{prefix}_{secret}"
    return plaintext, prefix, hash_key(plaintext)


class ApiKeyService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        organization_id: UUID,
        name: str,
        role: str,
        *,
        expires_at: datetime | None = None,
    ) -> tuple[ApiKeyRecord, str]:
        if role not in ROLE_SCOPES:
            raise AuthError(400, "unknown role")
        plaintext, prefix, key_hash = generate_key()
        record = ApiKeyRecord(
            organization_id=organization_id,
            key_prefix=prefix,
            key_hash=key_hash,
            name=name,
            role=role,
            scopes=json.dumps(sorted(ROLE_SCOPES[role])),
            status="active",
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return record, plaintext

    def list(self, organization_id: UUID) -> tuple[ApiKeyRecord, ...]:
        rows = self._session.scalars(
            select(ApiKeyRecord)
            .where(ApiKeyRecord.organization_id == organization_id)
            .order_by(ApiKeyRecord.created_at)
        ).all()
        return tuple(rows)

    def revoke(self, organization_id: UUID, key_id: UUID) -> bool:
        record = self._session.get(ApiKeyRecord, key_id)
        if record is None or record.organization_id != organization_id:
            return False
        record.status = "revoked"
        self._session.flush()
        return True

    def authenticate(self, plaintext: str) -> AuthContext:
        prefix = plaintext.split("_")[1] if plaintext.startswith("dfk_") else ""
        record = self._session.scalars(
            select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == prefix)
        ).first()
        if record is None or not secrets.compare_digest(record.key_hash, hash_key(plaintext)):
            raise AuthError(401, "invalid API key")
        if record.status != "active":
            raise AuthError(401, "API key is not active")
        if record.expires_at is not None and record.expires_at < datetime.now(UTC):
            raise AuthError(401, "API key has expired")
        record.last_used_at = datetime.now(UTC)
        self._session.flush()
        return AuthContext(
            organization_id=record.organization_id,
            scopes=frozenset(json.loads(record.scopes)),
            role=record.role,
            key_id=record.id,
        )


def write_audit(
    session: Session,
    *,
    action: str,
    outcome: str,
    request_id: str,
    organization_id: UUID | None = None,
    detail: str = "",
) -> None:
    session.add(
        SecurityAuditRecord(
            organization_id=organization_id,
            action=action,
            outcome=outcome,
            request_id=request_id,
            detail=detail[:512],
        )
    )
    session.flush()
