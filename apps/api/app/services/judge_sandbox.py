# Purpose: provision and resolve TTL-bound judge sandbox sessions.
# Responsibilities: mint one isolated fictional organization per judge session with a scoped judge
#   credential, evaluate expiry server-side, and produce the namespace every cache, job, export and
#   query key must be built from. Never stores judge-supplied content — identifiers, lifetime and
#   quota counters only.
# Dependencies: settings, records, api_keys. No HTTP, no route knowledge.
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.database.base import Base
from app.models.records import JudgeSandboxRecord
from app.services.api_keys import ApiKeyService

# The sandbox is fictional and disposable; a short lifetime bounds how long any judge-created record
# can persist and keeps an abandoned session from accumulating state indefinitely.
DEFAULT_SANDBOX_TTL_HOURS = 8

SANDBOX_LABEL = "DeceptiForge Judge Sandbox"

_KEY_PREFIX = "deceptiforge:judge"


class SandboxError(Exception):
    """Raised when a sandbox cannot be resolved. Carries a safe status and message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class SandboxNamespace:
    """The scope every judge-scoped key must be built from.

    Environment is part of the key so a development sandbox and a hosted judge sandbox can never
    collide in a shared Redis, even if an organization id were somehow reused. Organization and
    session are both present so that reusing an organization id across sessions — which the unique
    constraint forbids, but which a future change could reintroduce — still cannot alias two
    judges' keys onto each other.
    """

    environment: str
    organization_id: UUID
    session_id: UUID

    def key(self, *parts: str) -> str:
        """Build a namespaced key. Every part is included verbatim after the scope prefix."""
        if not parts:
            raise ValueError("a namespaced key requires at least one part")
        if any(not part for part in parts):
            raise ValueError("namespaced key parts must be non-empty")
        scope = (
            _KEY_PREFIX,
            self.environment,
            str(self.organization_id),
            str(self.session_id),
        )
        return ":".join((*scope, *parts))

    def owns(self, organization_id: UUID) -> bool:
        """Whether a record in this organization belongs to this sandbox."""
        return organization_id == self.organization_id


@dataclass(frozen=True)
class ProvisionedSandbox:
    """A freshly created sandbox. The plaintext key is returned once and never stored."""

    namespace: SandboxNamespace
    api_key: str
    expires_at: datetime
    record: JudgeSandboxRecord


class JudgeSandboxService:
    """Create, resolve and expire judge sandbox sessions."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ---- provisioning ----------------------------------------------------------------------

    def provision(self, *, ttl_hours: int = DEFAULT_SANDBOX_TTL_HOURS) -> ProvisionedSandbox:
        """Create an isolated sandbox: a new organization, a judge credential, and a deadline.

        The organization id is generated here and used nowhere else, so a judge starts with an
        empty namespace and cannot reach a tenant's records even if a query forgot its filter —
        there is nothing else in that organization to reach.
        """
        if ttl_hours <= 0:
            raise ValueError("sandbox ttl must be positive")
        now = datetime.now(UTC)
        organization_id = uuid4()
        session_id = uuid4()
        expires_at = now + timedelta(hours=ttl_hours)

        # The credential expires with the sandbox, so a leaked judge key cannot outlive the session
        # it was minted for. `issuer_scopes=None`: this is out-of-band provisioning, not a tenant
        # administrator minting a key, and `judge` is deliberately absent from
        # TENANT_GRANTABLE_ROLES.
        key_record, plaintext = ApiKeyService(self._session).create(
            organization_id,
            f"judge-sandbox-{session_id}",
            "judge",
            expires_at=expires_at,
        )

        record = JudgeSandboxRecord(
            organization_id=organization_id,
            session_id=session_id,
            environment=self._settings.app_env,
            api_key_id=key_record.id,
            label=SANDBOX_LABEL,
            status="active",
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()

        return ProvisionedSandbox(
            namespace=SandboxNamespace(
                environment=record.environment,
                organization_id=organization_id,
                session_id=session_id,
            ),
            api_key=plaintext,
            expires_at=expires_at,
            record=record,
        )

    # ---- resolution ------------------------------------------------------------------------

    def resolve(self, organization_id: UUID, *, now: datetime | None = None) -> JudgeSandboxRecord:
        """Return the live sandbox owning this organization, or raise.

        Expiry is decided here, from the stored deadline, so a client cannot extend its own session
        and an expired sandbox stops working without waiting for a cleanup sweep to run.
        """
        moment = now or datetime.now(UTC)
        record = self._session.execute(
            select(JudgeSandboxRecord).where(
                JudgeSandboxRecord.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if record is None:
            # Deliberately indistinguishable from "expired": neither answer should let a caller
            # probe which organization ids exist.
            raise SandboxError(404, "sandbox not found")
        if record.status != "active" or _expired(record, moment):
            raise SandboxError(410, "sandbox session has expired")
        return record

    def namespace_for(self, record: JudgeSandboxRecord) -> SandboxNamespace:
        return SandboxNamespace(
            environment=record.environment,
            organization_id=record.organization_id,
            session_id=record.session_id,
        )

    # ---- lifecycle -------------------------------------------------------------------------

    def expire_due(self, *, now: datetime | None = None, limit: int = 500) -> int:
        """Mark elapsed sandboxes expired. Idempotent; returns how many changed state."""
        moment = now or datetime.now(UTC)
        due = (
            self._session.execute(
                select(JudgeSandboxRecord)
                .where(
                    JudgeSandboxRecord.status == "active",
                    JudgeSandboxRecord.expires_at <= moment,
                )
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for record in due:
            record.status = "expired"
        return len(due)


def _expired(record: JudgeSandboxRecord, now: datetime) -> bool:
    deadline = record.expires_at
    if deadline.tzinfo is None:
        # SQLite round-trips naive datetimes; treat stored values as UTC rather than comparing
        # naive to aware and raising.
        deadline = deadline.replace(tzinfo=UTC)
    return deadline <= now


# ---- reset -----------------------------------------------------------------------------------

# Exactly the tables the judge workspace can cause rows in. An allowlist, not "everything in this
# organization": reset must never become a generic org-wipe that a future table silently joins.
#
# Deliberately ABSENT, and asserted so in tests:
#   ApiKeyRecord      — reset preserves authentication; deleting it would log the judge out.
#   JudgeSandboxRecord — preserves the organization assignment and the quota accounting, so reset
#                        restores data without refilling budget.
#   SecurityAuditRecord — the audit trail is append-only; a judge must not be able to erase it.
def _resettable_models() -> tuple[type[Base], ...]:
    from app.models.records import (
        AlertRecord,
        ContextProfileRecord,
        DecoyPlanRecord,
        DetectionEventRecord,
        IncidentRecord,
        NarrativeRevisionRecord,
        PlacementPlanRecord,
        ReconstructionJobRecord,
        RepositoryRecord,
        ValidationReportRecord,
    )

    return (
        # Deleted in dependency order: derived records first, source records last.
        NarrativeRevisionRecord,
        IncidentRecord,
        ReconstructionJobRecord,
        AlertRecord,
        DetectionEventRecord,
        ValidationReportRecord,
        DecoyPlanRecord,
        PlacementPlanRecord,
        ContextProfileRecord,
        RepositoryRecord,
    )


class SandboxResetService:
    """Clear a sandbox's own generated records, and nothing else."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reset(self, namespace: SandboxNamespace) -> dict[str, int]:
        """Delete this sandbox's generated records. Idempotent; returns per-table counts.

        Every statement is filtered on the sandbox's own organization id. Because that id is
        generated per session and used nowhere else, the filter cannot match a tenant's rows, a
        demo record, or another judge's data even if the caller lied about which sandbox they are:
        the organization comes from the resolved sandbox row, never from the request body.
        """
        deleted: dict[str, int] = {}
        for model in _resettable_models():
            result = self._session.execute(
                delete(model).where(
                    model.organization_id == namespace.organization_id  # type: ignore[attr-defined]
                )
            )
            deleted[str(model.__tablename__)] = int(getattr(result, "rowcount", 0) or 0)
        return deleted
