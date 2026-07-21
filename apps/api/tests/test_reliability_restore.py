# Purpose: verify restore-integrity checks (migration mismatch, org scope, encryption),
#   deterministic RPO/RTO, the checksummed report, and that backup metadata has no secrets.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.services.reliability import backup_meta, objectives, restore_verify

_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _settings(**over) -> Settings:  # type: ignore[no-untyped-def]
    base = dict(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        evidence_encryption_mode="local",
        evidence_encryption_key="k" * 40,
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _session(*, with_alembic: str | None = "0019_reliability") -> Session:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    s = sessionmaker(bind=e, expire_on_commit=False)()
    if with_alembic is not None:
        s.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)"))
        s.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": with_alembic})
        s.commit()
    return s


def test_verify_passes_on_good_restore() -> None:
    session = _session()
    checks = restore_verify.verify(session, _settings(), expected_migration="0019_reliability")
    by_name = {c.name: c for c in checks}
    assert by_name["tables_exist"].passed
    assert by_name["migration_revision"].passed
    assert by_name["organization_scope"].passed
    assert by_name["encryption_readable"].passed


def test_verify_detects_migration_mismatch() -> None:
    session = _session(with_alembic="0001_old")
    checks = restore_verify.verify(session, _settings(), expected_migration="0019_reliability")
    assert {c.name: c.passed for c in checks}["migration_revision"] is False


def test_verify_detects_missing_migration_table() -> None:
    session = _session(with_alembic=None)
    checks = restore_verify.verify(session, _settings(), expected_migration="0019_reliability")
    assert {c.name: c.passed for c in checks}["migration_revision"] is False


def test_report_checksum_is_deterministic() -> None:
    session = _session()
    checks = restore_verify.verify(session, _settings(), expected_migration="0019_reliability")
    r1 = restore_verify.build_report(
        drill_id="d",
        backup_identifier="b",
        recovery_point=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=10),
        achieved_rpo_minutes=2.0,
        achieved_rto_minutes=10.0,
        migration_revision="0019_reliability",
        checks=checks,
    )
    r2 = restore_verify.build_report(
        drill_id="d2",
        backup_identifier="b",
        recovery_point=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=10),
        achieved_rpo_minutes=2.0,
        achieved_rto_minutes=10.0,
        migration_revision="0019_reliability",
        checks=checks,
    )
    assert r1.checksum == r2.checksum and r1.passed is True


def test_rpo_rto_deterministic() -> None:
    rpo = objectives.achieved_rpo_minutes(_NOW, _NOW - timedelta(minutes=3))
    rto = objectives.achieved_rto_minutes(_NOW, _NOW + timedelta(minutes=42))
    assert rpo == 3.0 and rto == 42.0
    assert objectives.within_targets(rpo=3.0, rto=42.0, rpo_target=5, rto_target=60) is True
    assert objectives.within_targets(rpo=9.0, rto=42.0, rpo_target=5, rto_target=60) is False


def test_backup_metadata_has_no_secrets() -> None:
    session = _session()
    meta = backup_meta.backup_metadata(session, backup_identifier="backup-1")
    assert meta["migration_revision"] == "0019_reliability"
    # Table names may include 'api_keys'; the guard targets secret *values*, so this must not raise.
    backup_meta.assert_no_secrets(meta)
    # A metadata blob that leaked a secret value is rejected.
    import pytest

    with pytest.raises(ValueError, match="secret"):
        backup_meta.assert_no_secrets({"secret": "abc"})
