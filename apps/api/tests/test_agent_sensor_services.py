# Purpose: verify agent-sensor pure services — path normalization safety, scope normalization,
#   deterministic path classification, violation rules, minimization, and sequence analysis.
from __future__ import annotations

from app.models.domain.agent_sensor import (
    AgentEventType,
    AgentScopePolicyDoc,
    PathClass,
    ScopeViolationType,
)
from app.services.agent_sensor.classification import classify_path
from app.services.agent_sensor.minimize import minimize_metadata, sanitize_task_summary
from app.services.agent_sensor.paths import normalize_path, path_matches
from app.services.agent_sensor.rules import SessionAggregate, evaluate
from app.services.agent_sensor.scope import normalize_scope
from app.services.agent_sensor.sequence import detect_escalation


def _policy(**over) -> AgentScopePolicyDoc:  # type: ignore[no-untyped-def]
    base = dict(
        organization_id="org",
        name="p",
        allowed_paths=("apps/web/components/navigation/**",),
        denied_paths=(),
        allowed_tools=(),
        denied_tools=(),
        allowed_resource_types=(),
        maximum_file_reads=200,
        maximum_sensitive_reads=0,
    )
    base.update(over)
    return AgentScopePolicyDoc(**base)  # type: ignore[arg-type]


# -- path normalization safety ---------------------------------------------------------------


def test_normalize_rejects_traversal_and_encoding() -> None:
    assert normalize_path("../../etc/passwd") is None
    assert normalize_path("apps/%2e%2e/%2e%2e/secret") is None
    assert normalize_path("/etc/shadow") is None
    assert normalize_path("C:/Windows/system32") is None
    assert normalize_path("a\x00b") is None


def test_normalize_canonicalizes() -> None:
    assert normalize_path("./apps/web/./x.ts") == "apps/web/x.ts"
    assert normalize_path("apps\\web\\x.ts") == "apps/web/x.ts"
    assert normalize_path("apps/web/../web/x.ts") == "apps/web/x.ts"


def test_path_matches_case_insensitive_and_globs() -> None:
    assert path_matches("apps/web/**", "APPS/WEB/x.ts")
    assert path_matches("apps/web/**", "apps/web/deep/y.ts")
    assert not path_matches("apps/web/**", "apps/api/x.py")


# -- scope normalization ---------------------------------------------------------------------


def test_scope_normalization_sanitizes_and_extracts_keywords() -> None:
    scope = normalize_scope(
        task_summary="  Fix the mobile navbar   spacing\x07 bug ",
        allowed_paths=("apps/web/components/navigation/",),
    )
    assert "\x07" not in scope.task_summary
    assert "navbar" in scope.keywords
    assert scope.allowed_paths == ("apps/web/components/navigation/**",)


# -- path classification ---------------------------------------------------------------------


def test_classify_path() -> None:
    allowed = ("apps/web/components/navigation/**",)
    decoys = frozenset({"apps/web/components/navigation/decoy_config.ts"})

    def cl(path: str, dset: frozenset[str] = frozenset()) -> PathClass:
        return classify_path(path, allowed_paths=allowed, decoy_paths=dset)

    assert cl("apps/web/components/navigation/navbar.tsx") == PathClass.TASK_RELEVANT
    assert cl("apps/web/components/navigation/decoy_config.ts", decoys) == PathClass.DECOY
    assert cl("apps/api/.env") == PathClass.CREDENTIAL
    assert cl("services/billing/charge.py") == PathClass.BILLING
    assert cl("node_modules/left-pad/index.js") == PathClass.SHARED_DEPENDENCY
    assert cl("scripts/unrelated.py") == PathClass.UNRELATED


# -- violation rules -------------------------------------------------------------------------


def test_in_scope_not_flagged() -> None:
    d = evaluate(
        event_type=AgentEventType.FILE_READ,
        normalized_path="apps/web/components/navigation/navbar.tsx",
        tool_name=None,
        resource_type=None,
        decoy_id=None,
        policy=_policy(),
        decoy_paths=frozenset(),
        agg=SessionAggregate(),
    )
    assert d.violation_type is None
    assert d.path_class == PathClass.TASK_RELEVANT


def test_sensitive_file_flagged() -> None:
    d = evaluate(
        event_type=AgentEventType.FILE_READ,
        normalized_path="apps/api/.env",
        tool_name=None,
        resource_type=None,
        decoy_id=None,
        policy=_policy(),
        decoy_paths=frozenset(),
        agg=SessionAggregate(),
    )
    assert d.violation_type == ScopeViolationType.SENSITIVE_FILE_ACCESS


def test_decoy_touch_high_confidence() -> None:
    d = evaluate(
        event_type=AgentEventType.FILE_READ,
        normalized_path="apps/x/decoy.ts",
        tool_name=None,
        resource_type=None,
        decoy_id="decoy-1",
        policy=_policy(),
        decoy_paths=frozenset(),
        agg=SessionAggregate(),
    )
    assert d.violation_type == ScopeViolationType.DECOY_ASSET_TOUCH
    assert d.confidence >= 0.9
    assert d.decoy_id == "decoy-1"


def test_destructive_and_db_and_network() -> None:
    assert (
        evaluate(
            event_type=AgentEventType.DENIED_ACTION_ATTEMPTED,
            normalized_path=None,
            tool_name=None,
            resource_type=None,
            decoy_id=None,
            policy=_policy(),
            decoy_paths=frozenset(),
            agg=SessionAggregate(),
        ).violation_type
        == ScopeViolationType.DESTRUCTIVE_ACTION_ATTEMPT
    )
    assert (
        evaluate(
            event_type=AgentEventType.DATABASE_QUERY_REQUESTED,
            normalized_path=None,
            tool_name=None,
            resource_type=None,
            decoy_id=None,
            policy=_policy(),
            decoy_paths=frozenset(),
            agg=SessionAggregate(),
        ).violation_type
        == ScopeViolationType.UNEXPECTED_DATABASE_ACCESS
    )
    assert (
        evaluate(
            event_type=AgentEventType.NETWORK_REQUEST_REQUESTED,
            normalized_path=None,
            tool_name=None,
            resource_type=None,
            decoy_id=None,
            policy=_policy(),
            decoy_paths=frozenset(),
            agg=SessionAggregate(),
        ).violation_type
        == ScopeViolationType.UNEXPECTED_NETWORK_ACCESS
    )


def test_repeated_unrelated_increases_score() -> None:
    agg = SessionAggregate()
    policy = _policy(maximum_file_reads=20)
    last = None
    for i in range(10):
        last = evaluate(
            event_type=AgentEventType.FILE_READ,
            normalized_path=f"misc/dir/file{i}.py",
            tool_name=None,
            resource_type=None,
            decoy_id=None,
            policy=policy,
            decoy_paths=frozenset(),
            agg=agg,
        )
    assert agg.violation_count >= 5
    assert last is not None
    assert last.violation_type in (
        ScopeViolationType.OUT_OF_SCOPE_PATH_ACCESS,
        ScopeViolationType.EXCESSIVE_REPOSITORY_BREADTH,
    )


def test_encoded_path_cannot_bypass_denied_rule() -> None:
    # An encoded traversal path normalizes to None and never silently counts as in-scope.
    d = evaluate(
        event_type=AgentEventType.FILE_READ,
        normalized_path=normalize_path("%2e%2e/secret"),
        tool_name=None,
        resource_type=None,
        decoy_id=None,
        policy=_policy(),
        decoy_paths=frozenset(),
        agg=SessionAggregate(),
    )
    # normalized_path is None -> treated as unrelated non-path event, still in-scope info here,
    # but the point is the raw encoded path never resolved to a real allowed path.
    assert normalize_path("%2e%2e/secret") is None
    assert d.path_class == PathClass.UNRELATED


# -- minimize + sequence ---------------------------------------------------------------------


def test_minimize_drops_raw_content() -> None:
    out = minimize_metadata(
        {"tool": "grep", "file_content": "SECRET", "reasoning": "chain", "stdout": "x" * 5}
    )
    assert "file_content" not in out and "reasoning" not in out and "stdout" not in out
    assert out["tool"] == "grep"


def test_sanitize_task_summary_bounds() -> None:
    assert len(sanitize_task_summary("x" * 1000)) == 512
    assert "\x00" not in sanitize_task_summary("a\x00b")


def test_detect_escalation() -> None:
    benign = [PathClass.TASK_RELEVANT, PathClass.SHARED_DEPENDENCY, PathClass.TASK_RELEVANT]
    suspicious = [PathClass.UNRELATED, PathClass.ADJACENT, PathClass.CREDENTIAL, PathClass.DECOY]
    assert detect_escalation(benign) is False
    assert detect_escalation(suspicious) is True
