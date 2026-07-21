# Purpose: prove the database-honey lifecycle against the in-memory fake connector.
# Responsibilities: connector secrets encrypted; execute inserts + verifies + activates; monitoring
#   only after verification; idempotent retry inserts one row; failed insert fails safely; retire
#   deletes only the exact owned row; a modified row causes drift_detected; cross-org isolation.
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.database_honey import (
    ColumnInfo,
    HoneyDecoyType,
    HoneyDeploymentStatus,
    TableInfo,
)
from app.repositories.database_honey import ConnectorNotFoundError, DatabaseHoneyRepository
from app.services.database.connector_port import FakeDatabaseClient
from app.services.database.preview import build_preview
from app.services.database.service import DatabaseHoneyService


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
    )


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _customers() -> TableInfo:
    def col(name, dtype="varchar", **kw):  # type: ignore[no-untyped-def]
        return ColumnInfo(name=name, data_type=dtype, is_nullable=kw.pop("nullable", False), **kw)

    return TableInfo(
        schema_name="public",
        table_name="customers",
        columns=(
            col("id", "uuid", is_primary_key=True),
            col("email", "varchar", max_length=255),
            col("full_name", "varchar", max_length=120),
            col("status", "varchar", enum_values=("active", "inactive")),
        ),
        primary_key=("id",),
    )


class _Ctx:
    def __init__(self) -> None:
        self.settings = _settings()
        self.session: Session = sessionmaker(bind=_engine(), expire_on_commit=False)()
        self.repo = DatabaseHoneyRepository(self.session, self.settings)
        self.client = FakeDatabaseClient()
        self.client.register_table(_customers())
        self.org = uuid4()
        self.connector = self.repo.create_connector(
            organization_id=self.org,
            name="warehouse",
            host_reference="db.internal",
            database_name="app",
            secret_payload={"user": "deceptiforge_writer", "password": "x"},
            ssl_mode="require",
            read_only_mode=False,
            created_by_actor_id=uuid4(),
        )
        snapshot = self.client.discover_schema(
            _dummy_spec(), allowed_schemas=("public",), max_tables=100
        )
        self.snap_record = self.repo.add_snapshot(self.org, self.connector.id, snapshot)
        self.snapshot = snapshot
        self.record = self.repo.create_deployment(
            organization_id=self.org,
            connector_id=self.connector.id,
            schema_snapshot_id=self.snap_record.id,
            target_schema="public",
            target_table="customers",
            decoy_type=HoneyDecoyType.CUSTOMER.value,
            requested_by_actor_id=uuid4(),
            expires_at=None,
        )
        preview, _row = build_preview(
            deployment_id=str(self.record.id),
            connector_id=str(self.connector.id),
            snapshot=snapshot,
            schema="public",
            table="customers",
            decoy_type=HoneyDecoyType.CUSTOMER,
            trace_id="DFG-DB-1",
            allowed_schemas=("public",),
            blocked_patterns=tuple(self.settings.database_blocked_table_patterns),
            expires_at=None,
        )
        self.repo.set_preview(self.record, preview)
        self.svc = DatabaseHoneyService(self.repo, self.client, self.settings)

    def to_deploying(self) -> None:
        for target in (
            HoneyDeploymentStatus.AWAITING_APPROVAL,
            HoneyDeploymentStatus.APPROVED,
            HoneyDeploymentStatus.DEPLOYING,
        ):
            self.repo.transition(self.record, target)


def _dummy_spec():  # type: ignore[no-untyped-def]
    from app.services.database.connector_port import ConnectionSpec

    return ConnectionSpec("h", "d", "u", "p", "require", 5, 5000)


def test_connector_secret_is_encrypted() -> None:
    c = _Ctx()
    assert "password" not in c.connector.secret_ciphertext
    assert c.repo.resolve_secret(c.connector)["password"] == "x"  # round-trips in memory only


def test_execute_inserts_verifies_and_activates() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == HoneyDeploymentStatus.DEPLOYED.value
    assert c.record.monitoring_activated_at is not None
    assert c.client.row_count("public", "customers") == 1
    assert len(c.repo.records_for(c.record.id)) == 1


def test_execute_is_idempotent() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    assert c.client.row_count("public", "customers") == 1
    # Simulate a duplicate job that was queued before the first completed: force the status back to
    # deploying and re-run. The fingerprint guard must prevent a second insert.
    c.record.status = HoneyDeploymentStatus.DEPLOYING.value
    c.session.flush()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.client.row_count("public", "customers") == 1  # still one row
    assert len(c.repo.records_for(c.record.id)) == 1


def test_failed_insert_fails_safely_without_monitoring() -> None:
    c = _Ctx()
    c.client.fail_write = True
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == HoneyDeploymentStatus.FAILED.value
    assert c.record.monitoring_activated_at is None
    assert c.client.row_count("public", "customers") == 0
    assert len(c.repo.records_for(c.record.id)) == 0


def test_retire_deletes_only_the_owned_row() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    # An unrelated real row must survive.
    real = {
        "id": str(uuid4()),
        "email": "real@corp.example",
        "full_name": "Real",
        "status": "active",
    }
    c.client.insert_row(
        _dummy_spec(), schema="public", table="customers", values=real, pk_columns=("id",)
    )
    assert c.client.row_count("public", "customers") == 2
    c.repo.transition(c.record, HoneyDeploymentStatus.RETIRING)
    c.svc.retire(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == HoneyDeploymentStatus.RETIRED.value
    assert c.client.row_count("public", "customers") == 1  # only the honey row removed


def test_modified_row_triggers_drift_and_blocks_delete() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    honey = c.repo.records_for(c.record.id)[0]
    import json

    pk = json.loads(honey.target_primary_key)
    c.client.mutate_row("public", "customers", pk, status="tampered")
    c.repo.transition(c.record, HoneyDeploymentStatus.RETIRING)
    c.svc.retire(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == HoneyDeploymentStatus.DRIFT_DETECTED.value
    assert c.client.row_count("public", "customers") == 1  # not deleted


def test_cross_org_connector_rejected() -> None:
    c = _Ctx()
    import pytest

    with pytest.raises(ConnectorNotFoundError):
        c.repo.get_connector(uuid4(), c.connector.id)
