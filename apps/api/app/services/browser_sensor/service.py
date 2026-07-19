# Purpose: manage browser sensor enrollment, scoped credentials, and signed-request verification.
# Responsibilities: create one-time short-lived enrollment tokens (hash-only at rest), consume a
#   token atomically to provision a sensor identity + encrypted signing secret + a separate scoped
#   ingest API key, verify signed browser events (monitor-signature-v1) with org/status checks,
#   rotate the signing secret, and revoke a sensor. Never returns or logs secrets or signatures.
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
from app.models.domain.browser_sensor import SensorStatus, assert_transition
from app.models.records import (
    BrowserEnrollmentTokenRecord,
    BrowserSensorRecord,
)
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
    sensor: BrowserSensorRecord
    sensor_public_id: str
    signing_secret: str  # shown once
    api_key: str  # shown once


class BrowserSensorService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._cipher = secret_cipher(settings)

    # -- enrollment tokens --------------------------------------------------------------------

    def create_enrollment_token(
        self, organization_id: UUID, *, created_by_actor_id: UUID | None
    ) -> tuple[BrowserEnrollmentTokenRecord, str]:
        plaintext = secrets.token_urlsafe(24)
        ttl = self._settings.browser_sensor_enrollment_ttl_seconds
        record = BrowserEnrollmentTokenRecord(
            organization_id=organization_id,
            token_hash=_hash_token(plaintext),
            created_by_actor_id=created_by_actor_id,
            expires_at=_now() + timedelta(seconds=ttl),
        )
        self._session.add(record)
        self._session.flush()
        return record, plaintext

    def enroll(
        self,
        *,
        token: str,
        name: str,
        installation_id: str,
        browser_family: str,
        extension_version: str,
        device_label: str | None,
    ) -> EnrollmentResult:
        """Consume a one-time token and provision a sensor. Token is invalidated atomically."""
        record = self._session.scalars(
            select(BrowserEnrollmentTokenRecord).where(
                BrowserEnrollmentTokenRecord.token_hash == _hash_token(token)
            )
        ).first()
        if record is None:
            raise EnrollmentError(404, "unknown enrollment token")
        if record.consumed_at is not None:
            raise EnrollmentError(409, "enrollment token already used")
        if record.expires_at < _now():
            raise EnrollmentError(410, "enrollment token expired")
        # Atomic single-use consume: only the first writer flips consumed_at.
        result = self._session.execute(
            update(BrowserEnrollmentTokenRecord)
            .where(
                BrowserEnrollmentTokenRecord.id == record.id,
                BrowserEnrollmentTokenRecord.consumed_at.is_(None),
            )
            .values(consumed_at=_now())
        )
        if cast("CursorResult[Any]", result).rowcount != 1:
            raise EnrollmentError(409, "enrollment token already used")

        org = record.organization_id
        sensor_public_id = f"dfs_{secrets.token_hex(6)}"
        signing_secret = secrets.token_urlsafe(32)
        # Separate scoped ingest key — never a general dashboard key.
        api_key_record, api_key_plaintext = ApiKeyService(self._session).create(
            org, f"browser-sensor:{sensor_public_id}", "browser_sensor"
        )
        sensor = BrowserSensorRecord(
            organization_id=org,
            sensor_public_id=sensor_public_id,
            name=name[:128],
            installation_id=installation_id[:128],
            device_label=device_label[:128] if device_label else None,
            browser_family=browser_family[:32],
            extension_version=extension_version[:32],
            secret_ciphertext=self._cipher.encrypt(signing_secret),
            secret_key_version=self._cipher.key_version,
            status=SensorStatus.ACTIVE.value,
            api_key_id=api_key_record.id,
            last_seen_at=_now(),
        )
        self._session.add(sensor)
        self._session.flush()
        record.consumed_by_sensor_id = sensor.id
        self._session.flush()
        return EnrollmentResult(sensor, sensor_public_id, signing_secret, api_key_plaintext)

    # -- lifecycle ----------------------------------------------------------------------------

    def get(self, organization_id: UUID, sensor_id: UUID) -> BrowserSensorRecord | None:
        record = self._session.get(BrowserSensorRecord, sensor_id)
        if record is None or record.organization_id != organization_id:
            return None
        return record

    def list(self, organization_id: UUID) -> tuple[BrowserSensorRecord, ...]:
        return tuple(
            self._session.scalars(
                select(BrowserSensorRecord)
                .where(BrowserSensorRecord.organization_id == organization_id)
                .order_by(BrowserSensorRecord.created_at.desc())
            ).all()
        )

    def revoke(self, record: BrowserSensorRecord) -> None:
        assert_transition(SensorStatus(record.status), SensorStatus.REVOKED)
        record.status = SensorStatus.REVOKED.value
        record.updated_at = _now()
        # Revoke the scoped ingest key too, so it cannot authenticate at all.
        if record.api_key_id is not None:
            ApiKeyService(self._session).revoke(record.organization_id, record.api_key_id)
        self._session.flush()

    def rotate_secret(self, record: BrowserSensorRecord) -> str:
        """Rotate the signing secret; returns the new plaintext once. A revoked sensor cannot
        rotate."""
        if record.status == SensorStatus.REVOKED.value:
            raise EnrollmentError(409, "cannot rotate a revoked sensor")
        new_secret = secrets.token_urlsafe(32)
        record.secret_ciphertext = self._cipher.encrypt(new_secret)
        record.secret_key_version = self._cipher.key_version
        record.updated_at = _now()
        self._session.flush()
        return new_secret

    # -- signed ingestion ---------------------------------------------------------------------

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
            select(BrowserSensorRecord).where(
                BrowserSensorRecord.sensor_public_id == sensor_public_id
            )
        ).first()
        if record is None:
            raise SensorSignatureError(401, "unknown sensor")
        if record.organization_id != organization_id:
            raise SensorSignatureError(403, "sensor does not match organization")
        if record.status != SensorStatus.ACTIVE.value:
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

    def touch(self, record: BrowserSensorRecord, *, extension_version: str | None = None) -> None:
        record.last_seen_at = _now()
        if extension_version:
            record.extension_version = extension_version[:32]
        self._session.flush()
