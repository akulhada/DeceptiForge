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
        "coverage:export",
        "integrations:read",
        "integrations:manage",
        "integrations:test",
        "integrations:deliveries:read",
        "integrations:deliveries:retry",
        "incidents:export",
        "alerts:export",
        "usage:read",
        "limits:read",
        "onboarding:read",
        "onboarding:manage",
        "onboarding:run_detection_test",
        "onboarding:accept_recommendation",
        "onboarding:view_activation_metrics",
        "analysis:preview",
        "learning:read",
        "learning:feedback",
        "learning:calibrate",
        "learning:review",
        "learning:approve",
        "learning:activate",
        "learning:rollback",
        "admin:manage_keys",
        "admin:manage_monitors",
        "admin:read_audit",
    }
)

# Platform-only scopes are intentionally excluded from owner/admin tenant keys. They are provisioned
# out-of-band for the operations plane, so ordinary tenant administrators cannot read global
# capacity.
PLATFORM_PERMISSIONS: frozenset[str] = frozenset(
    {
        "capacity:read",
        "capacity:manage",
        "performance_runs:read",
        "performance_runs:execute",
        # Cross-tenant aggregate learning is operations-plane only; no tenant role may hold it.
        "learning:manage_global",
        # Control plane: reliability, regional failover/failback, backups, and global capacity are
        # infrastructure operations. A tenant role must never carry them, so they live only here.
        "platform:reliability",
        "platform:failover",
        "platform:failback",
        "platform:capacity",
        "platform:learning_global",
        "platform:organization_admin",
        "reliability:read",
        "backups:read",
        "restore_drills:run",
        "failover:request",
        "failover:approve",
        "failback:manage",
        "reliability_policy:manage",
        "organization_limits:manage",
    }
)

# ---- judge sandbox scopes ------------------------------------------------------------------------

# Judge scopes are deliberately EXCLUDED from PERMISSIONS. If they were members, the `owner` role
# (which is PERMISSIONS) would hand every tenant owner the sandbox-reset and controlled-interaction
# capabilities, and a
# judge credential would become indistinguishable from an ordinary tenant one. This mirrors how
# PLATFORM_PERMISSIONS is kept separate, and in the opposite direction: a judge holds none of
# PERMISSIONS' write scopes, and no tenant role holds any of these.
JUDGE_PERMISSIONS: frozenset[str] = frozenset(
    {
        # Enter the restricted workspace at all.
        "judge:workspace",
        # Run bounded analysis over approved structured signals. Distinct from `analysis:preview`,
        # which belongs to the development-only Analysis Lab.
        "judge:analyze",
        # Trigger ONE controlled interaction. The scope authorises asking the server to drive its
        # own pipeline; it deliberately does not include `monitoring:ingest`, so a judge credential
        # cannot post arbitrary events even to its own sandbox.
        "judge:interact",
        "judge:export",
        # Reset only the caller's own sandbox namespace.
        "judge:reset",
    }
)

# Reads a judge needs to inspect the result of their own bounded run. Enumerated rather than derived
# from _READS: that set includes connector, policy, billing and learning reads which a judge has no
# reason to hold.
_JUDGE_READS: frozenset[str] = frozenset(
    {
        "repositories:read",
        "placements:read",
        "decoys:read",
        "validation:read",
        "monitoring:read",
        "alerts:read",
        "incidents:read",
        "narratives:read",
    }
)

# Roles a tenant administrator may mint through /admin/api-keys. Sensor identities are provisioned
# at enrollment and platform roles are provisioned out-of-band, so neither is listed here.
TENANT_GRANTABLE_ROLES: tuple[str, ...] = ("viewer", "analyst", "admin", "owner", "service")
PLATFORM_ROLES: frozenset[str] = frozenset({"operator"})

# Separation of duties: whoever generates or reviews a candidate must not also approve/activate it.
_LEARNING_APPROVAL: frozenset[str] = frozenset({"learning:approve", "learning:activate"})

_READS = frozenset(p for p in PERMISSIONS if p.endswith(":read"))

ROLE_SCOPES: dict[str, frozenset[str]] = {
    "owner": PERMISSIONS,
    # Admin may generate and review calibration candidates but not approve/activate them; that
    # decision belongs to the owner (separation of duties).
    "admin": PERMISSIONS - _LEARNING_APPROVAL,
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
            "incidents:export",
            "alerts:export",
            "coverage:export",
            "analysis:preview",
            "learning:feedback",
        }
    ),
    "viewer": _READS | frozenset({"analysis:preview"}),
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
            "integrations:read",
            "integrations:deliveries:read",
            "integrations:deliveries:retry",
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
    # A judge credential is provisioned out-of-band per sandbox session, never minted by a tenant.
    # It holds no write scope on tenant data, no administration, and nothing from the platform
    # plane: the only mutations it can cause are the ones the sandbox endpoints perform on its own
    # namespace on its behalf.
    "judge": JUDGE_PERMISSIONS | _JUDGE_READS,
    "operator": PLATFORM_PERMISSIONS,
}

# Invariants that must hold for every build. Asserted here rather than only in tests so an
# inconsistent catalog cannot be imported at all.
assert not (JUDGE_PERMISSIONS & PERMISSIONS), "judge scopes must not leak into tenant roles"
assert not (JUDGE_PERMISSIONS & PLATFORM_PERMISSIONS), "judge scopes must not be platform scopes"
assert not (ROLE_SCOPES["judge"] & PLATFORM_PERMISSIONS), "judge must hold no platform scope"


def assert_grantable(issuer_scopes: frozenset[str], target_role: str) -> None:
    """Centralized rule for what a tenant issuer may mint.

    Fails closed on unknown roles, refuses platform and sensor roles outright, and refuses any role
    whose scopes exceed what the issuing actor itself holds — so a credential can never be minted
    with broader authority than its issuer.
    """
    if target_role not in ROLE_SCOPES:
        raise AuthError(400, "unknown role")
    if target_role in PLATFORM_ROLES:
        raise AuthError(403, "platform roles are not grantable through tenant administration")
    if target_role not in TENANT_GRANTABLE_ROLES:
        raise AuthError(403, "role is provisioned out-of-band and is not grantable here")
    target_scopes = ROLE_SCOPES[target_role]
    if target_scopes & PLATFORM_PERMISSIONS:
        raise AuthError(403, "platform permissions are not grantable through tenant administration")
    if not target_scopes <= issuer_scopes:
        raise AuthError(403, "cannot grant permissions beyond the issuing actor's own scope")


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


def _as_utc(moment: datetime) -> datetime:
    """Treat a stored deadline as UTC when the driver returns it without a timezone.

    Expiry is a security control. A backend that round-trips naive datetimes previously raised
    TypeError here, turning a 401 into a 500 — so an expired key produced a server error rather
    than a clean rejection, and the failure looked like a bug rather than a denied credential.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


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
        issuer_scopes: frozenset[str] | None = None,
        *,
        expires_at: datetime | None = None,
    ) -> tuple[ApiKeyRecord, str]:
        if role not in ROLE_SCOPES:
            raise AuthError(400, "unknown role")
        # When an issuer is known, the mint may never exceed what that issuer may grant.
        if issuer_scopes is not None:
            assert_grantable(issuer_scopes, role)
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
        if record.expires_at is not None and _as_utc(record.expires_at) < datetime.now(UTC):
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
