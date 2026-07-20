# Purpose: manage agent-sensor enrollment, scoped credentials, and signed-request verification.
# Responsibilities: create one-time short-lived enrollment tokens (hash-only), consume a token
#   atomically to provision a sensor identity + encrypted signing secret + a separate scoped ingest
#   API key (agent_sensor role), verify signed agent events (monitor-signature-v1) with org/status
#   checks, and revoke a sensor. Never returns or logs secrets or signatures.
# Dependencies: session, records, encryption, monitor signing, api keys, settings.
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.domain.agent_sensor import AgentSensorStatus, assert_transition
from app.models.records import AgentEnrollmentTokenRecord, AgentSensorRecord
from app.services.api_keys import ApiKeyService
from app.services.encryption import EncryptionError, secret_cipher
from app.services.monitor_signing import canonical_request, verify


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class EnrollmentError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class SensorSignatureError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class VerifiedSensor:
    sensor_id: UUID
    sensor_public_id: str
    organization_id: UUID


@dataclass(frozen=True)
class EnrollmentResult:
    sensor: AgentSensorRecord
    sensor_public_id: str
    signing_secret: str
    api_key: str


class AgentSensorService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._cipher = secret_cipher(settings)

    def create_enrollment_token(
        self, organization_id: UUID, *, created_by_actor_id: UUID | None
    ) -> tuple[AgentEnrollmentTokenRecord, str]:
        plaintext = secrets.token_urlsafe(24)
        ttl = self._settings.browser_sensor_enrollment_ttl_seconds
        record = AgentEnrollmentTokenRecord(
            organization_id=organization_id, token_hash=_hash_token(plaintext),
            created_by_actor_id=created_by_actor_id, expires_at=_now() + timedelta(seconds=ttl),
        )
        self._session.add(record)
        self._session.flush()
        return record, plaintext

    def enroll(
        self, *, token: str, name: str, adapter_type: str, version: str
    ) -> EnrollmentResult:
        record = self._session.scalars(
            select(AgentEnrollmentTokenRecord).where(
                AgentEnrollmentTokenRecord.token_hash == _hash_token(token)
            )
        ).first()
        if record is None:
            raise EnrollmentError(404, "unknown enrollment token")
        if record.consumed_at is not None:
            raise EnrollmentError(409, "enrollment token already used")
        expires = record.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < _now():
            raise EnrollmentError(410, "enrollment token expired")
        result = self._session.execute(
            update(AgentEnrollmentTokenRecord)
            .where(
                AgentEnrollmentTokenRecord.id == record.id,
                AgentEnrollmentTokenRecord.consumed_at.is_(None),
            )
            .values(consumed_at=_now())
        )
        if cast("CursorResult[Any]", result).rowcount != 1:
            raise EnrollmentError(409, "enrollment token already used")

        org = record.organization_id
        sensor_public_id = f"dfa_{secrets.token_hex(6)}"
        signing_secret = secrets.token_urlsafe(32)
        api_key_record, api_key_plaintext = ApiKeyService(self._session).create(
            org, f"agent-sensor:{sensor_public_id}", "agent_sensor"
        )
        sensor = AgentSensorRecord(
            organization_id=org, sensor_public_id=sensor_public_id, name=name[:128],
            adapter_type=adapter_type[:48], version=version[:32],
            secret_ciphertext=self._cipher.encrypt(signing_secret),
            secret_key_version=self._cipher.key_version, status=AgentSensorStatus.ACTIVE.value,
            api_key_id=api_key_record.id, last_seen_at=_now(),
        )
        self._session.add(sensor)
        self._session.flush()
        record.consumed_by_sensor_id = sensor.id
        self._session.flush()
        return EnrollmentResult(sensor, sensor_public_id, signing_secret, api_key_plaintext)

    def get(self, organization_id: UUID, sensor_id: UUID) -> AgentSensorRecord | None:
        record = self._session.get(AgentSensorRecord, sensor_id)
        if record is None or record.organization_id != organization_id:
            return None
        return record

    def list(self, organization_id: UUID) -> tuple[AgentSensorRecord, ...]:
        return tuple(
            self._session.scalars(
                select(AgentSensorRecord)
                .where(AgentSensorRecord.organization_id == organization_id)
                .order_by(AgentSensorRecord.created_at.desc())
            ).all()
        )

    def revoke(self, record: AgentSensorRecord) -> None:
        assert_transition(AgentSensorStatus(record.status), AgentSensorStatus.REVOKED)
        record.status = AgentSensorStatus.REVOKED.value
        record.updated_at = _now()
        if record.api_key_id is not None:
            ApiKeyService(self._session).revoke(record.organization_id, record.api_key_id)
        self._session.flush()

    def verify_request(
        self,
        *,
        organization_id: UUID,
        sensor_public_id: str | None,
        timestamp: str | None,
        nonce: str | None,
        signature: str | None,
        method: str,
        path: str,
        body: bytes,
    ) -> VerifiedSensor:
        if not (sensor_public_id and timestamp and nonce and signature):
            raise SensorSignatureError(401, "missing sensor signature headers")
        record = self._session.scalars(
            select(AgentSensorRecord).where(
                AgentSensorRecord.sensor_public_id == sensor_public_id
            )
        ).first()
        if record is None:
            raise SensorSignatureError(401, "unknown sensor")
        if record.organization_id != organization_id:
            raise SensorSignatureError(403, "sensor does not match organization")
        if record.status != AgentSensorStatus.ACTIVE.value:
            raise SensorSignatureError(401, "sensor is not active")
        try:
            secret = self._cipher.decrypt(record.secret_ciphertext)
        except EncryptionError as error:
            raise SensorSignatureError(500, "sensor credential unreadable") from error
        canonical = canonical_request(
            method=method, path=path, organization_id=str(organization_id),
            monitor_id=sensor_public_id, timestamp=timestamp, nonce=nonce, body=body,
        )
        if not verify(secret, canonical, signature):
            raise SensorSignatureError(401, "invalid sensor signature")
        record.last_seen_at = _now()
        self._session.flush()
        return VerifiedSensor(record.id, sensor_public_id, organization_id)

    def touch(self, record: AgentSensorRecord, *, version: str | None = None) -> None:
        record.last_seen_at = _now()
        if version:
            record.version = version[:32]
        self._session.flush()
