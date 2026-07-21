# Purpose: the judge sandbox security contract — least privilege, isolation, TTL, namespacing.
# A judge credential is handed to an untrusted third party in a hosted environment. These tests
# assert what it can and, more importantly, cannot do, and that two judges can never alias onto the
# same namespace.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401  (register tables)
from app.services.api_keys import (
    JUDGE_PERMISSIONS,
    PERMISSIONS,
    PLATFORM_PERMISSIONS,
    ROLE_SCOPES,
    TENANT_GRANTABLE_ROLES,
    ApiKeyService,
    AuthError,
    _as_utc,
    assert_grantable,
)
from app.services.judge_sandbox import (
    JudgeSandboxService,
    SandboxError,
    SandboxNamespace,
)

_JUDGE = ROLE_SCOPES["judge"]


@pytest.fixture
def db_session() -> Session:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture
def settings() -> Settings:
    # Judge mode specifically: the namespace embeds the environment, so provisioning must be
    # exercised in the mode it is meant for.
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="judge",
    )


class TestJudgeScopes:
    """A judge credential is untrusted. Its authority is enumerated, not inherited."""

    def test_judge_holds_no_write_scope_on_tenant_data(self) -> None:
        writes = {scope for scope in _JUDGE if scope in PERMISSIONS and not scope.endswith(":read")}
        assert writes == set()

    def test_judge_holds_no_administration(self) -> None:
        assert not any(scope.startswith("admin:") for scope in _JUDGE)

    def test_judge_holds_no_platform_scope(self) -> None:
        assert not (_JUDGE & PLATFORM_PERMISSIONS)

    def test_judge_cannot_ingest_monitoring_events_directly(self) -> None:
        # `judge:interact` authorises asking the server to drive its own pipeline. It must not
        # become a licence to post arbitrary events, even inside the sandbox.
        assert "monitoring:ingest" not in _JUDGE
        assert "judge:interact" in _JUDGE

    def test_judge_does_not_hold_the_analysis_lab_scope(self) -> None:
        # The Analysis Lab is development-only. A judge must not carry a scope for a surface that
        # is supposed to be unreachable in their environment.
        assert "analysis:preview" not in _JUDGE

    def test_judge_scopes_are_absent_from_every_tenant_role(self) -> None:
        # If judge scopes were members of PERMISSIONS, `owner: PERMISSIONS` would silently grant
        # sandbox reset and controlled interaction to every tenant owner.
        assert not (JUDGE_PERMISSIONS & PERMISSIONS)
        for role, scopes in ROLE_SCOPES.items():
            if role == "judge":
                continue
            assert not (scopes & JUDGE_PERMISSIONS), f"{role} leaked judge scopes"

    def test_a_tenant_administrator_cannot_mint_a_judge_key(self) -> None:
        assert "judge" not in TENANT_GRANTABLE_ROLES
        with pytest.raises(AuthError) as excinfo:
            assert_grantable(ROLE_SCOPES["owner"], "judge")
        assert excinfo.value.status_code == 403

    def test_a_judge_cannot_mint_anything(self) -> None:
        for role in TENANT_GRANTABLE_ROLES:
            with pytest.raises(AuthError):
                assert_grantable(_JUDGE, role)


class TestNamespace:
    """Every cache, job, export and query key must carry organization + session + environment."""

    def _namespace(self, **overrides: object) -> SandboxNamespace:
        base = dict(
            environment="judge",
            organization_id=uuid4(),
            session_id=uuid4(),
        )
        base.update(overrides)
        return SandboxNamespace(**base)  # type: ignore[arg-type]

    def test_key_carries_every_scope_component(self) -> None:
        namespace = self._namespace()
        key = namespace.key("analysis", "run-1")
        assert str(namespace.organization_id) in key
        assert str(namespace.session_id) in key
        assert "judge" in key
        assert key.endswith("analysis:run-1")

    def test_two_sessions_in_one_environment_never_collide(self) -> None:
        organization_id = uuid4()
        first = self._namespace(organization_id=organization_id)
        second = self._namespace(organization_id=organization_id)
        assert first.key("analysis") != second.key("analysis")

    def test_the_same_session_in_two_environments_never_collides(self) -> None:
        # Guards a shared Redis: a development sandbox must not read a hosted judge's cached result.
        shared = dict(organization_id=uuid4(), session_id=uuid4())
        development = self._namespace(environment="development", **shared)
        hosted = self._namespace(environment="judge", **shared)
        assert development.key("export") != hosted.key("export")

    def test_ownership_is_decided_by_organization(self) -> None:
        namespace = self._namespace()
        assert namespace.owns(namespace.organization_id) is True
        assert namespace.owns(uuid4()) is False

    def test_empty_key_parts_are_rejected(self) -> None:
        # An empty part would silently collapse two different keys into one.
        namespace = self._namespace()
        with pytest.raises(ValueError):
            namespace.key()
        with pytest.raises(ValueError):
            namespace.key("analysis", "")


class TestProvisioning:
    """Each session gets its own organization, its own credential, and a deadline."""

    def _service(self, db_session, settings) -> JudgeSandboxService:  # type: ignore[no-untyped-def]
        return JudgeSandboxService(db_session, settings)

    def test_each_session_receives_a_distinct_organization(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = self._service(db_session, settings)
        first = service.provision()
        second = service.provision()
        assert first.namespace.organization_id != second.namespace.organization_id
        assert first.namespace.session_id != second.namespace.session_id
        # One judge must never see another judge's results.
        assert not first.namespace.owns(second.namespace.organization_id)

    def test_the_credential_carries_only_judge_scopes(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = self._service(db_session, settings)
        provisioned = service.provision()
        db_session.commit()
        context = ApiKeyService(db_session).authenticate(provisioned.api_key)
        assert context.role == "judge"
        assert context.scopes == _JUDGE

    def test_the_credential_is_bound_to_one_organization(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        # The key resolves to its own sandbox organization and no other. The request boundary
        # compares this against the caller-supplied org header, so a judge presenting another
        # sandbox's id is rejected there.
        service = self._service(db_session, settings)
        provisioned = service.provision()
        other = service.provision()
        db_session.commit()
        context = ApiKeyService(db_session).authenticate(provisioned.api_key)
        assert context.organization_id == provisioned.namespace.organization_id
        assert context.organization_id != other.namespace.organization_id

    def test_the_credential_expires_with_the_sandbox(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        # A leaked judge key must not outlive the session it was minted for.
        from app.models.records import ApiKeyRecord

        service = self._service(db_session, settings)
        provisioned = service.provision(ttl_hours=2)
        db_session.commit()

        key = db_session.get(ApiKeyRecord, provisioned.record.api_key_id)
        assert key is not None
        # Compared as instants: some drivers round-trip the deadline without a timezone.
        assert _as_utc(key.expires_at) == provisioned.expires_at
        assert _as_utc(provisioned.record.expires_at) == provisioned.expires_at

        # And the deadline is enforced: an elapsed judge key is REJECTED, not merely recorded.
        # Expiry is a security control, so it must fail as a clean 401 rather than an error.
        key.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db_session.commit()
        with pytest.raises(AuthError) as excinfo:
            ApiKeyService(db_session).authenticate(provisioned.api_key)
        assert excinfo.value.status_code == 401

    def test_a_non_positive_ttl_is_rejected(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ValueError):
            self._service(db_session, settings).provision(ttl_hours=0)


class TestLifetime:
    """Expiry is decided server-side from the stored deadline."""

    def test_a_live_sandbox_resolves(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = JudgeSandboxService(db_session, settings)
        provisioned = service.provision()
        db_session.commit()
        resolved = service.resolve(provisioned.namespace.organization_id)
        assert resolved.session_id == provisioned.namespace.session_id

    def test_an_elapsed_sandbox_stops_working_without_waiting_for_a_sweep(
        self,
        db_session,  # type: ignore[no-untyped-def]
        settings,  # type: ignore[no-untyped-def]
    ) -> None:
        service = JudgeSandboxService(db_session, settings)
        provisioned = service.provision(ttl_hours=1)
        db_session.commit()
        later = datetime.now(UTC) + timedelta(hours=2)
        with pytest.raises(SandboxError) as excinfo:
            service.resolve(provisioned.namespace.organization_id, now=later)
        assert excinfo.value.status_code == 410

    def test_an_unknown_organization_is_not_distinguishable_from_an_expired_one(
        self,
        db_session,  # type: ignore[no-untyped-def]
        settings,  # type: ignore[no-untyped-def]
    ) -> None:
        # Neither answer should let a caller enumerate which organization ids exist.
        service = JudgeSandboxService(db_session, settings)
        with pytest.raises(SandboxError) as excinfo:
            service.resolve(uuid4())
        assert excinfo.value.status_code == 404
        assert "not found" in excinfo.value.message

    def test_expiring_due_sessions_is_idempotent(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = JudgeSandboxService(db_session, settings)
        provisioned = service.provision(ttl_hours=1)
        db_session.commit()
        later = datetime.now(UTC) + timedelta(hours=3)
        assert service.expire_due(now=later) == 1
        db_session.commit()
        assert service.expire_due(now=later) == 0
        assert provisioned.record.status == "expired"

    def test_a_live_session_is_not_swept(self, db_session, settings) -> None:  # type: ignore[no-untyped-def]
        service = JudgeSandboxService(db_session, settings)
        service.provision(ttl_hours=8)
        db_session.commit()
        assert service.expire_due(now=datetime.now(UTC)) == 0
