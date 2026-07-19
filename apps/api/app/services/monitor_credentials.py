# Purpose: manage monitor signing credentials and verify signed monitoring requests.
# Responsibilities: create credentials (returning the plaintext secret exactly once), store the
#   secret encrypted at rest, list/revoke credentials, and verify a monitor-signature-v1 request in
#   constant time while enforcing organization scope, status, and expiry. Never logs or returns the
#   secret or the signature. Dependencies: session, records, encryption, monitor_signing, settings.
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.records import MonitorCredentialRecord
from app.services.encryption import EncryptionError, secret_cipher
from app.services.monitor_signing import canonical_request, verify


@dataclass(frozen=True)
class VerifiedMonitor:
    credential_id: UUID
    monitor_id: str
    organization_id: UUID


class MonitorSignatureError(Exception):
    """Raised when a monitor request cannot be authenticated; carries a safe HTTP status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def generate_monitor_identity() -> tuple[str, str]:
    """Return (monitor_id, plaintext_secret). The secret is shown to the caller only once."""
    return f"dfm_{secrets.token_hex(6)}", secrets.token_urlsafe(32)


class MonitorCredentialService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._cipher = secret_cipher(settings)

    def create(
        self,
        organization_id: UUID,
        name: str,
        *,
        expires_at: datetime | None = None,
    ) -> tuple[MonitorCredentialRecord, str]:
        monitor_id, secret = generate_monitor_identity()
        record = MonitorCredentialRecord(
            organization_id=organization_id,
            monitor_id=monitor_id,
            name=name,
            secret_ciphertext=self._cipher.encrypt(secret),
            secret_key_version=self._cipher.key_version,
            status="active",
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return record, secret

    def list(self, organization_id: UUID) -> tuple[MonitorCredentialRecord, ...]:
        rows = self._session.scalars(
            select(MonitorCredentialRecord)
            .where(MonitorCredentialRecord.organization_id == organization_id)
            .order_by(MonitorCredentialRecord.created_at)
        ).all()
        return tuple(rows)

    def revoke(self, organization_id: UUID, credential_id: UUID) -> bool:
        record = self._session.get(MonitorCredentialRecord, credential_id)
        if record is None or record.organization_id != organization_id:
            return False
        record.status = "revoked"
        self._session.flush()
        return True

    def verify_request(
        self,
        *,
        organization_id: UUID,
        monitor_id: str | None,
        timestamp: str | None,
        nonce: str | None,
        signature: str | None,
        method: str,
        path: str,
        body: bytes,
    ) -> VerifiedMonitor:
        """Verify a signed monitoring request; raise MonitorSignatureError on any failure."""
        if not (monitor_id and timestamp and nonce and signature):
            raise MonitorSignatureError(401, "missing monitor signature headers")
        record = self._session.scalars(
            select(MonitorCredentialRecord).where(
                MonitorCredentialRecord.monitor_id == monitor_id
            )
        ).first()
        if record is None:
            raise MonitorSignatureError(401, "unknown monitor credential")
        # Cross-organization credential use is rejected before any secret is touched.
        if record.organization_id != organization_id:
            raise MonitorSignatureError(403, "monitor credential does not match organization")
        if record.status != "active":
            raise MonitorSignatureError(401, "monitor credential is not active")
        if record.expires_at is not None and record.expires_at < datetime.now(UTC):
            raise MonitorSignatureError(401, "monitor credential has expired")
        try:
            secret = self._cipher.decrypt(record.secret_ciphertext)
        except EncryptionError as error:
            raise MonitorSignatureError(500, "monitor credential unreadable") from error
        canonical = canonical_request(
            method=method,
            path=path,
            organization_id=str(organization_id),
            monitor_id=monitor_id,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        if not verify(secret, canonical, signature):
            raise MonitorSignatureError(401, "invalid monitor signature")
        record.last_used_at = datetime.now(UTC)
        self._session.flush()
        return VerifiedMonitor(record.id, monitor_id, organization_id)
