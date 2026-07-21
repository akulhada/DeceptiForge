# Purpose: the deployment-mode contract — which surfaces may exist in which environment.
# The judge environment is hosted and internet-reachable, so it must keep every production security
# control; it differs from production only in that the curated demo story may be mounted. These
# tests exist to stop a future change from treating "judge" as a development mode.
from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.config.settings import DEPLOYMENT_MODES, Settings
from app.routes.router import build_api_router

# A configuration satisfying every startup guard, so a failure below is attributable to the control
# under test rather than to unrelated production requirements.
_HARDENED = dict(
    auth_enabled=True,
    demo_enabled=False,
    analysis_lab_enabled=False,
    judge_workspace_enabled=False,
    rate_limit_mode="gateway",
    replay_backend="redis",
    redis_url="redis://localhost:6379/0",
    evidence_encryption_mode="local",
    evidence_encryption_key="test-evidence-key-0000000000000000000000",
    redis_fail_mode="closed",
    monitor_signature_required=True,
)

_HOSTED_MODES = ["judge", "staging", "production"]


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_HARDENED, **overrides})  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup validation pings Redis. These tests assert configuration policy, not connectivity."""
    monkeypatch.setattr(Settings, "_verify_redis_reachable", lambda self: None)


def _paths(settings: Settings) -> set[str]:
    """Return the paths this configuration actually exposes.

    Read from the generated OpenAPI document rather than walking `app.routes`: that is the same
    surface a client can reach, so a route cannot be "mounted but invisible" or vice versa.
    """
    app = FastAPI()
    app.include_router(build_api_router(settings))
    return set(app.openapi()["paths"])


def test_unknown_mode_is_rejected_rather_than_defaulting_to_permissive() -> None:
    # A typo must not resolve to "not development" and silently pick some middle behaviour.
    with pytest.raises(ValidationError):
        _settings(app_env="prod")
    with pytest.raises(ValidationError):
        _settings(app_env="")


def test_every_declared_mode_is_constructible() -> None:
    for mode in DEPLOYMENT_MODES:
        assert _settings(app_env=mode).app_env == mode


@pytest.mark.parametrize("mode", _HOSTED_MODES)
def test_hosted_modes_are_production_like(mode: str) -> None:
    settings = _settings(app_env=mode)
    assert settings.is_production_like is True
    # The judge environment must never be mistaken for a development one: every dev convenience in
    # the codebase (demo-key auth bypass, plaintext HTTP, private-network export, local path scan)
    # is gated on is_development.
    assert settings.is_development is False
    assert settings.allows_local_path_scan is False


@pytest.mark.parametrize("mode", _HOSTED_MODES)
def test_hosted_modes_keep_every_production_guard(mode: str) -> None:
    for override, fragment in (
        ({"redis_fail_mode": "open"}, "REDIS_FAIL_MODE"),
        ({"auth_enabled": False}, "AUTH_ENABLED"),
        ({"monitor_signature_required": False}, "MONITOR_SIGNATURE_REQUIRED"),
    ):
        with pytest.raises(RuntimeError) as excinfo:
            _settings(app_env=mode, **override).validate_runtime()
        assert fragment in str(excinfo.value)


class TestDemoSurface:
    """The curated demo may exist in development and judge only, and never without its flag."""

    @pytest.mark.parametrize("mode", ["development", "judge"])
    def test_eligible_modes_mount_it_when_enabled(self, mode: str) -> None:
        settings = _settings(app_env=mode, demo_enabled=True)
        settings.validate_runtime()
        assert settings.allows_demo_surface is True
        assert any(path.startswith("/demo") for path in _paths(settings))

    @pytest.mark.parametrize("mode", ["development", "judge"])
    def test_eligible_modes_still_require_the_flag(self, mode: str) -> None:
        settings = _settings(app_env=mode, demo_enabled=False)
        assert not any(path.startswith("/demo") for path in _paths(settings))

    @pytest.mark.parametrize("mode", ["staging", "production"])
    def test_tenant_deployments_refuse_it_at_startup(self, mode: str) -> None:
        settings = _settings(app_env=mode, demo_enabled=True)
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_runtime()
        assert "DEMO_ENABLED" in str(excinfo.value)

    @pytest.mark.parametrize("mode", ["staging", "production"])
    def test_the_router_refuses_it_independently_of_startup(self, mode: str) -> None:
        # Defence in depth: even if validate_runtime were skipped, the routes must not mount.
        settings = _settings(app_env=mode, demo_enabled=True)
        assert settings.allows_demo_surface is False
        assert not any(path.startswith("/demo") for path in _paths(settings))


class TestAnalysisLab:
    """The Analysis Lab is an internal fixture surface: development and test only, never hosted."""

    @pytest.mark.parametrize("mode", ["development", "test"])
    def test_internal_modes_may_mount_it(self, mode: str) -> None:
        settings = _settings(app_env=mode, analysis_lab_enabled=True)
        assert settings.allows_analysis_lab is True
        assert any("/analysis" in path for path in _paths(settings))

    @pytest.mark.parametrize("mode", _HOSTED_MODES)
    def test_hosted_modes_refuse_it_at_startup(self, mode: str) -> None:
        settings = _settings(app_env=mode, analysis_lab_enabled=True)
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_runtime()
        assert "ANALYSIS_LAB_ENABLED" in str(excinfo.value)

    @pytest.mark.parametrize("mode", _HOSTED_MODES)
    def test_hosted_modes_do_not_mount_it_even_if_the_flag_is_set(self, mode: str) -> None:
        # This is the control that makes /analysis-lab a 404 for judges rather than merely hidden
        # from the navigation.
        settings = _settings(app_env=mode, analysis_lab_enabled=True)
        assert settings.allows_analysis_lab is False
        assert not any("/analysis" in path for path in _paths(settings))

    def test_judge_never_gets_the_lab_even_alongside_the_demo(self) -> None:
        settings = _settings(app_env="judge", demo_enabled=True, analysis_lab_enabled=False)
        settings.validate_runtime()
        paths = _paths(settings)
        assert any(path.startswith("/demo") for path in paths)
        assert not any("/analysis" in path for path in paths)


def test_the_test_harness_agrees_with_the_settings_contract() -> None:
    """conftest duplicates the production-like set to default signing on. Keep them in step.

    If a new hosted mode were added to Settings but not to conftest, every test in that mode would
    silently run with unsigned ingestion permitted.
    """
    from tests.conftest import _PRODUCTION_LIKE_MODES

    for mode in DEPLOYMENT_MODES:
        assert _settings(app_env=mode).is_production_like == (mode in _PRODUCTION_LIKE_MODES)
