# Purpose: verify bootstrap-key shutdown controls and the evidence encryption boundary.
# Responsibilities: confirm env bootstrap keys are disabled by default, honored only inside an
#   open/unexpired window (and audited), that production refuses to start with unrestricted
#   bootstrap keys, and that sensitive evidence is encrypted before persistence (no plaintext in the
#   stored blob) while round-tripping. Dependencies: client factory, Settings, repository, records.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.operations import AlertEvidence, MonitorType, NormalizedAlert, Severity
from app.models.records import AlertRecord, SecurityAuditRecord
from app.repositories.artifacts import ArtifactRepository
from app.services.encryption import (
    EncryptionError,
    LocalEncryptionProvider,
    NoopEncryptionProvider,
    build_encryption_provider,
)

_ORG = "11111111-1111-1111-1111-111111111111"
_BINDINGS = f'{{"bootstrap-secret-key": "{_ORG}"}}'


# ---- bootstrap keys ------------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    return {"X-DeceptiForge-API-Key": "bootstrap-secret-key", "X-DeceptiForge-Org-Id": _ORG}


def test_bootstrap_key_disabled_by_default(make_client) -> None:  # type: ignore[no-untyped-def]
    with make_client(
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        api_key_bindings=_BINDINGS,
        bootstrap_keys_enabled=False,  # explicitly closed
    ) as client:
        assert client.get("/incidents", headers=_headers()).status_code == 401


def test_bootstrap_key_authenticates_when_window_open(make_client) -> None:  # type: ignore[no-untyped-def]
    with make_client(
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        api_key_bindings=_BINDINGS,
        bootstrap_keys_enabled=True,
    ) as client:
        assert client.get("/incidents", headers=_headers()).status_code == 200
        # The bootstrap authentication is audited.
        session = client.app_session()
        actions = session.scalars(select(SecurityAuditRecord.action)).all()
        session.close()
        assert "bootstrap_auth_used" in actions


def test_bootstrap_key_rejected_after_expiry(make_client) -> None:  # type: ignore[no-untyped-def]
    with make_client(
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        api_key_bindings=_BINDINGS,
        bootstrap_keys_enabled=True,
        bootstrap_expires_at="2000-01-01T00:00:00+00:00",  # already past
    ) as client:
        assert client.get("/incidents", headers=_headers()).status_code == 401


def _prod(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@localhost/db",
        "app_env": "production",
        "auth_enabled": True,
        "rate_limit_mode": "gateway",
        "replay_backend": "redis",
        "redis_url": "fakeredis://bootstrap-tests",
        "evidence_encryption_mode": "local",
        "monitor_signature_required": True,
        "api_key_bindings": {"k": _ORG},
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_production_refuses_unrestricted_bootstrap_keys() -> None:
    with pytest.raises(RuntimeError, match="bootstrap API keys are enabled in production"):
        _prod(bootstrap_keys_enabled=True, bootstrap_expires_at=None).validate_runtime()


def test_production_allows_time_boxed_bootstrap_window() -> None:
    # A bootstrap window with an expiry is permitted (the documented temporary-bootstrap procedure).
    _prod(
        bootstrap_keys_enabled=True,
        bootstrap_expires_at=datetime.now(UTC) + timedelta(hours=1),
    ).validate_runtime()


# ---- evidence encryption -------------------------------------------------------------------------


def test_local_provider_round_trips_and_hides_plaintext() -> None:
    provider = LocalEncryptionProvider("a-strong-key")
    token = provider.encrypt("SENSITIVE-EXCERPT")
    assert "SENSITIVE-EXCERPT" not in token  # ciphertext does not contain the plaintext
    assert provider.decrypt(token) == "SENSITIVE-EXCERPT"
    assert token.startswith("local:")  # self-describing mode + key version


def test_local_provider_rejects_tampered_token() -> None:
    provider = LocalEncryptionProvider("a-strong-key")
    with pytest.raises(EncryptionError):
        provider.decrypt("local:kdeadbeef:not-a-valid-fernet-token")


def test_build_provider_requires_key_and_rejects_unknown_mode() -> None:
    with pytest.raises(RuntimeError, match="requires EVIDENCE_ENCRYPTION_KEY"):
        build_encryption_provider(
            Settings(
                database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
                app_env="development",
                evidence_encryption_mode="local",
                evidence_encryption_key=None,
            )
        )


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _alert(secret: str) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier="DFG-A",
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="t",
        summary="observed",
        source_monitor=MonitorType.REPOSITORY,
        confidence=0.9,
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        event_count=1,
        deduplication_key="DFG-A:id:repository:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=secret, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def test_sensitive_evidence_is_encrypted_before_persistence() -> None:
    engine = _engine()
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repo = ArtifactRepository(session, encryption=LocalEncryptionProvider("evidence-key"))
    org = uuid4()
    secret = "TOPSECRET-EXFIL-MARKER"
    repo.add_alert(org, _alert(secret))
    session.commit()

    # The raw stored blob must not contain the plaintext excerpt.
    stored = session.scalars(select(AlertRecord.data)).all()
    assert stored and all(secret not in blob for blob in stored)
    assert all(not blob.startswith("{") for blob in stored)  # not plaintext JSON

    # Reading back through the repository decrypts and recovers the evidence.
    (alert,) = repo.alerts_for_organization(org)
    assert alert.evidence[0].excerpt == secret


def test_noop_provider_is_reversible_encoding() -> None:
    provider = NoopEncryptionProvider()
    token = provider.encrypt("value")
    assert provider.decrypt(token) == "value"
    assert token.startswith("disabled:")
