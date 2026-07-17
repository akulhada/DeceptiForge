from app.models.domain.decoy import DecoyKind
from app.models.domain.intelligence import (
    DocumentationCulture,
    OrganizationArchetype,
    OrganizationContextProfile,
    PlacementPlan,
    PlacementRecommendation,
    PlacementTargetType,
    RepositoryIntelligenceProfile,
    StackMaturity,
)
from app.services.believability import BelievabilitySafetyEngine
from app.services.decoy_generation import DecoyGenerationPlanner
from app.services.monitoring import MonitoringInstrumentationEngine


def prepared():
    context = OrganizationContextProfile(
        repository_name="payments",
        organization_archetype=OrganizationArchetype.APPLICATION_SERVICE,
        stack_maturity=StackMaturity.ESTABLISHED,
        ai_exposure_risk=0,
        database_sensitivity_confidence=0,
        documentation_culture=DocumentationCulture.NONE,
        operational_complexity="low",
        confidence=0.9,
    )
    repository = RepositoryIntelligenceProfile(
        repository_name="payments", root_path="/repo", is_git_repository=True, file_count=1
    )
    placement = PlacementRecommendation(
        target_type=PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE,
        target_location=".env.example",
        placement_priority=0.9,
        confidence=0.9,
        reasoning=("accepted",),
        expected_detection_quality=0.9,
        risk_score=0.1,
        expected_attacker_agent_visibility=0.9,
        expected_false_positive_risk=0.1,
        future_asset_type_recommendation=DecoyKind.SECRET,
    )
    asset = (
        DecoyGenerationPlanner()
        .generate(
            repository,
            context,
            PlacementPlan(
                repository_name="payments", context=context, recommendations=(placement,)
            ),
        )
        .assets[0]
    )
    report = BelievabilitySafetyEngine().evaluate(asset, context, repository, placement)
    return asset, report


def test_only_accepted_decoys_are_registered_and_can_be_disabled() -> None:
    asset, report = prepared()
    engine = MonitoringInstrumentationEngine()
    warned = report.model_copy(update={"decision": "warn"})

    plan = engine.register((asset,), (warned,))
    assert plan.registrations == ()
    assert plan.rejected_decoy_ids == (asset.decoy_id,)
    plan = engine.register((asset,), (report,))
    assert plan.registrations
    assert engine.active_tripwires()[0].trace_identifier == asset.trigger_metadata.trace_identifier
    assert engine.disable(asset.trigger_metadata.trace_identifier)
    assert engine.active_tripwires() == ()


def test_exact_normalized_and_duplicate_detection_minimize_evidence() -> None:
    asset, report = prepared()
    engine = MonitoringInstrumentationEngine()
    engine.register((asset,), (report,))
    trace = asset.trigger_metadata.trace_identifier

    exact = engine.scan_file_content("docs/a.md", f"prefix {trace} suffix")
    normalized = engine.scan_repository_file("src/a.py", trace.replace("-", "_"))

    assert exact is not None and exact.confidence == 1 and len(exact.observed_value_excerpt) <= 256
    assert normalized is not None and normalized.confidence == 0.85
    assert engine.scan_file_content("docs/a.md", f"prefix {trace} suffix") is None
    assert engine.scan_text("nothing", "paste") is None


def test_database_monitor_and_health_are_available_without_external_listeners() -> None:
    asset, report = prepared()
    engine = MonitoringInstrumentationEngine()
    engine.register((asset,), (report,))

    event = engine.scan_database_payload("export.json", asset.trigger_metadata.trace_identifier)

    assert event is not None
    assert event.monitor_type.value == "database_payload"
    assert all(item.status.value == "active" for item in engine.health())
