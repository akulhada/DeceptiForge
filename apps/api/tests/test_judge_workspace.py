# Purpose: the judge workspace contract — budgets, scoped reset, bounded input, and mounting.
# The workspace is reachable by an untrusted third party in a hosted environment, so these tests
# assert the blast radius of every action: what it may spend, what it may delete, and what it may
# send.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401  (register tables)
from app.models.records import (
    AlertRecord,
    ApiKeyRecord,
    JudgeSandboxRecord,
    RepositoryRecord,
    SecurityAuditRecord,
)
from app.routes.router import build_api_router
from app.services.judge_quota import ANALYZE, EXPORT, INTERACT, RESET, JudgeQuotaService
from app.services.judge_sandbox import (
    JudgeSandboxService,
    SandboxNamespace,
    SandboxResetService,
    _resettable_models,
)


@pytest.fixture
def db_session() -> Session:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="judge",
    )


class TestQuotas:
    """Budgets are per session, survive reset, and only advertise Retry-After when it helps."""

    def _sandbox(self, db_session: Session, settings: Settings) -> JudgeSandboxRecord:
        provisioned = JudgeSandboxService(db_session, settings).provision()
        db_session.commit()
        return provisioned.record

    def test_actions_are_allowed_while_under_budget(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        record = self._sandbox(db_session, settings)
        quota = JudgeQuotaService(settings)
        for action in (ANALYZE, INTERACT, EXPORT):
            assert quota.check(record, action) is None

    def test_an_exhausted_budget_is_refused(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        record = self._sandbox(db_session, settings)
        quota = JudgeQuotaService(settings)
        for _ in range(settings.judge_max_analysis_runs):
            quota.consume(record, ANALYZE)
        denial = quota.check(record, ANALYZE)
        assert denial is not None
        assert denial.reason == "budget_exhausted"

    def test_an_exhausted_budget_carries_no_retry_after(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        # Waiting cannot refill a session budget, so telling the client to retry would be a lie.
        record = self._sandbox(db_session, settings)
        quota = JudgeQuotaService(settings)
        for _ in range(settings.judge_max_interactions):
            quota.consume(record, INTERACT)
        denial = quota.check(record, INTERACT)
        assert denial is not None
        assert denial.retry_after_seconds is None
        assert "new sandbox session" in denial.detail

    def test_reset_cooldown_carries_a_usable_retry_after(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        record = self._sandbox(db_session, settings)
        quota = JudgeQuotaService(settings)
        now = datetime.now(UTC)
        assert quota.check(record, RESET, now=now) is None
        quota.consume(record, RESET, now=now)

        denial = quota.check(record, RESET, now=now + timedelta(seconds=5))
        assert denial is not None
        assert denial.reason == "cooldown"
        assert denial.retry_after_seconds is not None
        # Sleeping exactly that long must clear the cooldown, not land one call short.
        cleared = now + timedelta(seconds=5 + denial.retry_after_seconds)
        assert quota.check(record, RESET, now=cleared) is None

    def test_budgets_belong_to_one_session_only(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = JudgeSandboxService(db_session, settings)
        first = service.provision()
        second = service.provision()
        db_session.commit()
        quota = JudgeQuotaService(settings)
        for _ in range(settings.judge_max_analysis_runs):
            quota.consume(first.record, ANALYZE)
        # One judge exhausting their budget must not spend another judge's.
        assert quota.check(first.record, ANALYZE) is not None
        assert quota.check(second.record, ANALYZE) is None

    def test_an_unknown_action_is_rejected_rather_than_allowed(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        record = self._sandbox(db_session, settings)
        quota = JudgeQuotaService(settings)
        with pytest.raises(ValueError):
            quota.check(record, "deploy")
        with pytest.raises(ValueError):
            quota.consume(record, "deploy")


class TestScopedReset:
    """Reset clears the sandbox's own records and nothing else."""

    def _seed(self, db_session: Session, organization_id) -> None:  # type: ignore[no-untyped-def]
        db_session.add(
            RepositoryRecord(
                organization_id=organization_id,
                name="fictional-fixture",
                root_path="fictional/acme-payments",
                profile="{}",
            )
        )
        db_session.add(
            AlertRecord(
                id=uuid4(),
                organization_id=organization_id,
                trace_identifier=f"trace-{uuid4()}",
                decoy_id=uuid4(),
                data="{}",
            )
        )
        db_session.commit()

    def _repositories(  # type: ignore[no-untyped-def]
        self, db_session: Session, organization_id
    ) -> list[RepositoryRecord]:
        return list(
            db_session.execute(
                select(RepositoryRecord).where(
                    RepositoryRecord.organization_id == organization_id
                )
            )
            .scalars()
            .all()
        )

    def test_reset_restores_the_predefined_data(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        provisioned = JudgeSandboxService(db_session, settings).provision()
        db_session.commit()
        # A judge's own extra work, on top of the predefined seed.
        self._seed(db_session, provisioned.namespace.organization_id)

        SandboxResetService(db_session).reset(provisioned.namespace)
        db_session.commit()

        # Back to a known good starting point: the predefined fixture only, with the judge's own
        # records gone. Reset restores, it does not empty.
        org = provisioned.namespace.organization_id
        names = {row.name for row in self._repositories(db_session, org)}
        assert names == {"acme-payments"}

    def test_reset_never_touches_another_organization(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = JudgeSandboxService(db_session, settings)
        mine = service.provision()
        theirs = service.provision()
        tenant_organization_id = uuid4()  # an ordinary tenant, not a sandbox at all
        db_session.commit()
        self._seed(db_session, mine.namespace.organization_id)
        self._seed(db_session, theirs.namespace.organization_id)
        self._seed(db_session, tenant_organization_id)

        SandboxResetService(db_session).reset(mine.namespace)
        db_session.commit()

        # The other judge keeps both their predefined seed and their own work; the tenant keeps
        # theirs untouched. Neither is a sandbox reset can reach.
        their_names = {
            row.name for row in self._repositories(db_session, theirs.namespace.organization_id)
        }
        assert their_names == {"acme-payments", "fictional-fixture"}, "reset hit another sandbox"
        tenant_names = {row.name for row in self._repositories(db_session, tenant_organization_id)}
        assert tenant_names == {"fictional-fixture"}, "reset escaped into a tenant organization"

    def test_reset_preserves_authentication_and_accounting(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        provisioned = JudgeSandboxService(db_session, settings).provision()
        db_session.commit()
        JudgeQuotaService(settings).consume(provisioned.record, ANALYZE)
        db_session.commit()

        SandboxResetService(db_session).reset(provisioned.namespace)
        db_session.commit()

        # The judge must still be logged in, still own their organization, and NOT get their
        # budget back — otherwise reset becomes an infinite-quota button.
        key = db_session.get(ApiKeyRecord, provisioned.record.api_key_id)
        assert key is not None and key.status == "active"
        sandbox = db_session.get(JudgeSandboxRecord, provisioned.record.id)
        assert sandbox is not None
        assert sandbox.organization_id == provisioned.namespace.organization_id
        assert sandbox.analysis_runs == 1

    def test_reset_cannot_erase_the_audit_trail(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        provisioned = JudgeSandboxService(db_session, settings).provision()
        db_session.add(
            SecurityAuditRecord(
                organization_id=provisioned.namespace.organization_id,
                action="authz",
                outcome="rejected",
                request_id="r1",
                detail="missing judge:reset",
            )
        )
        db_session.commit()

        SandboxResetService(db_session).reset(provisioned.namespace)
        db_session.commit()

        rows = (
            db_session.execute(
                select(SecurityAuditRecord).where(
                    SecurityAuditRecord.organization_id
                    == provisioned.namespace.organization_id
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "a judge must not be able to delete their own audit trail"

    def test_reset_is_idempotent(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        # Idempotent in END STATE, not in delete counts: every reset re-seeds, so the second call
        # removes what the first one restored and lands on the same place again.
        provisioned = JudgeSandboxService(db_session, settings).provision()
        db_session.commit()
        self._seed(db_session, provisioned.namespace.organization_id)
        service = SandboxResetService(db_session)

        service.reset(provisioned.namespace)
        db_session.commit()
        org = provisioned.namespace.organization_id
        after_first = {r.name for r in self._repositories(db_session, org)}

        service.reset(provisioned.namespace)
        db_session.commit()
        after_second = {r.name for r in self._repositories(db_session, org)}

        assert after_first == after_second == {"acme-payments"}

    def test_the_reset_allowlist_excludes_identity_and_audit(self) -> None:
        # Guards against a future table joining the sweep by accident.
        names = {model.__tablename__ for model in _resettable_models()}
        assert "api_keys" not in names
        assert "judge_sandboxes" not in names
        assert "security_audit" not in names

    def test_reset_is_scoped_by_the_resolved_organization_not_the_request(self) -> None:
        # The namespace is built from the resolved sandbox row, so a caller cannot aim it elsewhere.
        namespace = SandboxNamespace(
            environment="judge", organization_id=uuid4(), session_id=uuid4()
        )
        assert namespace.owns(namespace.organization_id)
        assert not namespace.owns(uuid4())


class TestMounting:
    """The workspace exists in development and judge, and nowhere else."""

    _HARDENED = dict(
        auth_enabled=True,
        demo_enabled=False,
        analysis_lab_enabled=False,
        rate_limit_mode="gateway",
        replay_backend="redis",
        redis_url="redis://localhost:6379/0",
        evidence_encryption_mode="local",
        evidence_encryption_key="test-evidence-key-0000000000000000000000",
        redis_fail_mode="closed",
        monitor_signature_required=True,
    )

    def _paths(self, **overrides: object) -> set[str]:
        settings = Settings(**{**self._HARDENED, **overrides})  # type: ignore[arg-type]
        app = FastAPI()
        app.include_router(build_api_router(settings))
        return set(app.openapi()["paths"])

    @pytest.mark.parametrize("mode", ["development", "judge"])
    def test_eligible_modes_mount_it_when_enabled(self, mode: str) -> None:
        paths = self._paths(app_env=mode, judge_workspace_enabled=True)
        assert any("/judge" in path for path in paths)

    @pytest.mark.parametrize("mode", ["development", "judge"])
    def test_eligible_modes_still_require_the_flag(self, mode: str) -> None:
        assert not any(
            "/judge" in path for path in self._paths(app_env=mode, judge_workspace_enabled=False)
        )

    @pytest.mark.parametrize("mode", ["staging", "production", "test"])
    def test_other_modes_never_mount_it(self, mode: str) -> None:
        assert not any(
            "/judge" in path for path in self._paths(app_env=mode, judge_workspace_enabled=True)
        )

    @pytest.mark.parametrize("mode", ["staging", "production"])
    def test_tenant_deployments_refuse_the_flag_at_startup(self, monkeypatch, mode: str) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(Settings, "_verify_redis_reachable", lambda self: None)
        settings = Settings(**{**self._HARDENED, "app_env": mode, "judge_workspace_enabled": True})  # type: ignore[arg-type]
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_runtime()
        assert "JUDGE_WORKSPACE_ENABLED" in str(excinfo.value)
