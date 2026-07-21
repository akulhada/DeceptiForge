# Purpose: orchestrate the deterministic preview pipeline for the Interactive Demo Lab.
# Responsibilities: validate-mapped signals -> context engine -> placement engine -> sensitive-zone
#   ranking -> confidence -> warnings -> explainable response. Times each stage. No GPT, no scan,
#   no persistence, no mutation of deployment/alert/incident/monitoring state.
# Dependencies: mapping, sensitive_zones, quality, context + placement engines, response models.
from __future__ import annotations

import time
from datetime import UTC, datetime

from app.models.domain.analysis_preview import (
    ENGINE_VERSIONS,
    SCHEMA_VERSION,
    AnalysisPreviewResponse,
    CalibrationAttribution,
    ConfidenceBreakdown,
    ContextProfileView,
    InferredField,
    InputSummary,
    PlacementRecommendationView,
    VocabularyView,
)
from app.models.domain.analysis_signals import (
    KNOWN_TOP_LEVEL_FIELDS,
    RepositorySignals,
)
from app.models.domain.intelligence import OrganizationContextProfile, PlacementPlan
from app.models.domain.learning import FEATURE_SCHEMA_VERSION
from app.services.analysis_lab.mapping import signals_to_profile
from app.services.analysis_lab.quality import (
    compute_confidence,
    domain_conflict_score,
    generate_warnings,
)
from app.services.analysis_lab.sensitive_zones import rank_sensitive_zones
from app.services.context_engine import ContextEngine
from app.services.learning.applied import ActiveCalibration, apply_calibration
from app.services.placement_reasoning import PlacementReasoningEngine

_DOMAIN_LABELS: dict[str, str] = {
    "fintech": "Financial / payments platform",
    "healthcare": "Healthcare application",
    "ecommerce": "E-commerce platform",
    "saas_crm": "SaaS customer-management system",
    "ml_data": "Data / ML platform",
}
_DOMAIN_KEYWORDS: dict[str, frozenset[str]] = {
    "fintech": frozenset({"payment", "billing", "ledger", "settlement", "reconciliation", "psp"}),
    "healthcare": frozenset({"patient", "clinical", "provider", "claims", "scheduling"}),
    "ecommerce": frozenset({"catalog", "order", "cart", "checkout", "fulfillment", "inventory"}),
    "saas_crm": frozenset({"tenant", "subscription", "account", "crm", "workspace"}),
    "ml_data": frozenset({"embedding", "vector", "model", "pipeline", "feature", "retrieval"}),
}


def _terms(signals: RepositorySignals) -> set[str]:
    out: set[str] = set()
    if signals.naming_patterns is not None:
        for t in (
            *signals.naming_patterns.domain_terms,
            *signals.naming_patterns.entity_names,
            *signals.naming_patterns.team_terms,
        ):
            out.add(t.lower())
    for s in signals.services:
        out.add(s.name.lower())
    for db in signals.databases:
        for t in db.data_domain_terms:
            out.add(t.lower())
    return out


def _infer_business_domain(signals: RepositorySignals) -> InferredField:
    terms = _terms(signals)
    scored = sorted(
        ((len(terms & kw), name) for name, kw in _DOMAIN_KEYWORDS.items() if terms & kw),
        reverse=True,
    )
    if not scored:
        return InferredField(
            key="probable_business_domain",
            value="unknown",
            confidence=0.0,
            reason="No business-domain vocabulary present; no domain fabricated.",
        )
    hits, name = scored[0]
    matched = sorted(terms & _DOMAIN_KEYWORDS[name])
    conflict, _ = domain_conflict_score(signals)
    conf = round(min(1.0, 0.4 + 0.15 * hits) * (1 - 0.5 * conflict), 4)
    return InferredField(
        key="probable_business_domain",
        value=_DOMAIN_LABELS[name],
        confidence=conf,
        supporting_signals=tuple(matched)[:10],
        reason=f"Domain vocabulary {', '.join(matched[:5])} appeared across services and terms."
        + (" Conflicting domain terms reduced confidence." if conflict else ""),
    )


def _infer_repo_type(signals: RepositorySignals, ctx: OrganizationContextProfile) -> InferredField:
    services = len(signals.services)
    k8s = bool(signals.infrastructure and signals.infrastructure.orchestration)
    domains = sum(1 for kw in _DOMAIN_KEYWORDS.values() if _terms(signals) & kw)
    if domains >= 2 and services >= 3:
        value, reason = (
            "monorepo",
            "Multiple business domains and several services indicate a monorepo.",
        )
    elif services >= 3 and k8s:
        value, reason = "microservices", "Several independently named services plus orchestration."
    elif services >= 3:
        value, reason = "service-oriented", "Multiple named services without orchestration signals."
    else:
        value, reason = "application", "Few services; a single application is most likely."
    conf = round(min(1.0, 0.4 + 0.1 * services), 4)
    return InferredField(
        key="probable_repository_type",
        value=value,
        confidence=conf,
        supporting_signals=(f"services={services}", f"orchestration={k8s}"),
        reason=reason,
    )


def _infer_stack(signals: RepositorySignals) -> InferredField:
    langs = [s.name for s in signals.languages][:3]
    fws = [s.name for s in signals.frameworks][:3]
    parts = langs + fws
    if not parts:
        return InferredField(
            key="dominant_technical_stack",
            value="unknown",
            confidence=0.0,
            reason="No language or framework signals provided.",
        )
    return InferredField(
        key="dominant_technical_stack",
        value=", ".join(parts),
        confidence=round(min(1.0, 0.4 + 0.1 * len(parts)), 4),
        supporting_signals=tuple(parts),
        reason="Dominant stack from provided language/framework signals.",
    )


def _infer_service_arch(signals: RepositorySignals) -> InferredField:
    services = len(signals.services)
    k8s = bool(signals.infrastructure and signals.infrastructure.orchestration)
    if services >= 3 and k8s:
        value, conf = "microservices", 0.8
        reason = (
            "Kubernetes manifests and several independently named services increased confidence."
        )
    elif services >= 2:
        value, conf = "multi-service", 0.6
        reason = "Multiple services without strong orchestration evidence."
    else:
        value, conf = "monolithic-or-single-service", 0.5
        reason = "Insufficient service signals for a distributed architecture."
    return InferredField(
        key="service_architecture",
        value=value,
        confidence=conf,
        supporting_signals=(f"services={services}", f"orchestration={k8s}"),
        reason=reason,
    )


def _infer_operational_maturity(
    signals: RepositorySignals, ctx: OrganizationContextProfile
) -> InferredField:
    doc = signals.documentation
    doc_signals = (
        0
        if doc is None
        else sum(
            len(g)
            for g in (
                doc.runbook_paths,
                doc.architecture_paths,
                doc.operational_paths,
                doc.support_paths,
                doc.policy_paths,
            )
        )
    )
    ci = bool(signals.infrastructure and signals.infrastructure.ci_cd)
    if doc_signals >= 4 and ci:
        value, conf = "mature", 0.75
    elif doc_signals >= 1 or ci:
        value, conf = "developing", 0.55
    else:
        value, conf = "unknown", 0.2
    return InferredField(
        key="operational_maturity",
        value=value,
        confidence=conf,
        supporting_signals=(f"doc_signals={doc_signals}", f"ci_cd={ci}"),
        reason="Maturity inferred from documentation breadth and CI/CD presence.",
    )


_REGULATED_TERMS = frozenset(
    {
        "payment",
        "billing",
        "ledger",
        "settlement",
        "patient",
        "clinical",
        "claims",
        "phi",
        "pci",
        "card",
        "credential",
        "secret",
    }
)


def _infer_data_sensitivity(signals: RepositorySignals) -> InferredField:
    secrets = len(signals.secret_locations)
    dbs = len(signals.databases)
    # Regulated / high-value domains (payments, healthcare, secrets) raise sensitivity beyond raw
    # counts — a small fintech or healthcare repo is still high-sensitivity.
    regulated = bool(_terms(signals) & _REGULATED_TERMS) or any(
        s.category
        and any(t in s.category.lower() for t in ("payment", "phi", "credential", "secret"))
        for s in signals.secret_locations
    )
    score = min(1.0, 0.2 * secrets + 0.15 * dbs + (0.4 if regulated else 0.0))
    value = "high" if score >= 0.6 else "moderate" if score >= 0.3 else "low"
    return InferredField(
        key="data_sensitivity",
        value=value,
        confidence=round(min(1.0, 0.4 + score), 4),
        supporting_signals=(
            f"secret_locations={secrets}",
            f"databases={dbs}",
            f"regulated={regulated}",
        ),
        reason="Sensitivity from secret/database density plus regulated-domain indicators.",
    )


def _infer_deployment_model(signals: RepositorySignals) -> InferredField:
    infra = signals.infrastructure
    if infra is None:
        return InferredField(
            key="deployment_model",
            value="unknown",
            confidence=0.1,
            reason="No infrastructure signals provided.",
        )
    if infra.orchestration:
        value, conf, reason = (
            "orchestrated (kubernetes-style)",
            0.75,
            "Orchestration signals present.",
        )
    elif infra.container_tools:
        value, conf, reason = "containerized", 0.6, "Container tooling without orchestration."
    elif infra.cloud_indicators:
        value, conf, reason = (
            "cloud-hosted",
            0.55,
            "Cloud indicators without container/orchestration.",
        )
    else:
        value, conf, reason = "unspecified", 0.3, "Infrastructure block present but sparse."
    return InferredField(
        key="deployment_model",
        value=value,
        confidence=conf,
        supporting_signals=tuple(
            infra.orchestration or infra.container_tools or infra.cloud_indicators
        )[:6],
        reason=reason,
    )


def _infer_ai_exposure(
    signals: RepositorySignals, ctx: OrganizationContextProfile
) -> InferredField:
    surfaces = [s.surface_type for s in signals.ai_surfaces]
    conf = round(ctx.ai_exposure_risk, 4)
    value = "elevated" if conf >= 0.7 else "present" if surfaces else "none"
    reason = (
        "RAG/MCP indicators and vector-store references raised AI-surface exposure."
        if surfaces
        else "No AI surfaces provided."
    )
    return InferredField(
        key="ai_system_exposure",
        value=value,
        confidence=conf,
        supporting_signals=tuple(dict.fromkeys(surfaces))[:6],
        reason=reason,
    )


def _context_view(
    signals: RepositorySignals, ctx: OrganizationContextProfile, zones_categories: tuple[str, ...]
) -> ContextProfileView:
    interests = tuple(ctx.high_value_systems)[:8] or zones_categories[:5]
    return ContextProfileView(
        probable_business_domain=_infer_business_domain(signals),
        probable_repository_type=_infer_repo_type(signals, ctx),
        dominant_technical_stack=_infer_stack(signals),
        service_architecture=_infer_service_arch(signals),
        operational_maturity=_infer_operational_maturity(signals, ctx),
        data_sensitivity=_infer_data_sensitivity(signals),
        deployment_model=_infer_deployment_model(signals),
        ai_system_exposure=_infer_ai_exposure(signals, ctx),
        high_value_attacker_interests=interests,
    )


def _vocabulary_view(signals: RepositorySignals, ctx: OrganizationContextProfile) -> VocabularyView:
    naming = signals.naming_patterns
    domain_terms = tuple(dict.fromkeys(naming.domain_terms))[:30] if naming else ()
    entity_names = tuple(dict.fromkeys(naming.entity_names))[:30] if naming else ()
    env_terms = tuple(dict.fromkeys(naming.environment_terms))[:20] if naming else ()
    service_names = tuple(dict.fromkeys(s.name for s in signals.services))[:30]
    prefixes = tuple(naming.prefixes)[:20] if naming else ()
    suffixes = tuple(naming.suffixes)[:20] if naming else ()
    op_vocab = tuple(v.value for v in ctx.primary_technical_vocabulary)[:30]
    influence = []
    if domain_terms:
        influence.append("Domain terms shape decoy terminology instead of generic templates.")
    if service_names:
        influence.append("Service names suggest plausible file names and placement folders.")
    if env_terms:
        influence.append("Environment terms guide realistic secret/config decoy naming.")
    confidence = round(
        min(1.0, 0.15 + 0.03 * (len(domain_terms) + len(entity_names) + len(service_names))), 4
    )
    return VocabularyView(
        domain_terms=domain_terms,
        entity_names=entity_names,
        service_names=service_names,
        environment_terms=env_terms,
        operational_vocabulary=op_vocab,
        prefixes=prefixes,
        suffixes=suffixes,
        confidence=confidence,
        supporting_signals=(f"domain={len(domain_terms)}", f"services={len(service_names)}"),
        influence_notes=tuple(influence),
    )


def _placement_views(
    plan: PlacementPlan, max_recommendations: int
) -> tuple[PlacementRecommendationView, ...]:
    rejected = tuple(
        f"{r.target_type.value}:{r.target_location}" for r in plan.rejected_candidates
    )[:10]
    views: list[PlacementRecommendationView] = []
    for rank, rec in enumerate(plan.recommendations[:max_recommendations], start=1):
        views.append(
            PlacementRecommendationView(
                rank=rank,
                zone=rec.target_type.value,
                proposed_path_or_pattern=rec.target_location[:512],
                decoy_type=rec.future_asset_type_recommendation.value,
                expected_visibility=rec.expected_attacker_agent_visibility,
                business_relevance=rec.placement_priority,
                detection_value=rec.expected_detection_quality,
                deployment_risk=rec.risk_score,
                confidence=rec.confidence,
                supporting_signals=tuple(rec.evidence)[:20],
                reasoning=" ".join(rec.reasoning)[:512],
                lower_ranked_alternatives=rejected,
            )
        )
    return tuple(views)


class AnalysisPreviewService:
    """Deterministic, stateless preview analysis. Safe to construct per request."""

    def __init__(self) -> None:
        self._context = ContextEngine()
        self._placement = PlacementReasoningEngine()

    def analyze(
        self,
        signals: RepositorySignals,
        *,
        organization_id: str,
        request_id: str,
        scenario_id: str | None = None,
        ignored_fields: tuple[str, ...] = (),
        max_recommendations: int = 10,
        minimum_confidence: float = 0.0,
        calibration: ActiveCalibration | None = None,
    ) -> AnalysisPreviewResponse:
        timings: dict[str, float] = {}

        def stage(name: str, fn):  # type: ignore[no-untyped-def]
            start = time.perf_counter()
            result = fn()
            timings[name] = round((time.perf_counter() - start) * 1000, 3)
            return result

        profile = stage("mapping", lambda: signals_to_profile(signals))
        context = stage("context_engine", lambda: self._context.build(profile))
        plan = stage("placement_reasoning", lambda: self._placement.plan(profile, context))
        zones = stage("sensitive_zones", lambda: rank_sensitive_zones(signals))
        placements = _placement_views(plan, max_recommendations)
        if minimum_confidence > 0:
            placements = tuple(p for p in placements if p.confidence >= minimum_confidence)
            placements = tuple(
                p.model_copy(update={"rank": i}) for i, p in enumerate(placements, 1)
            )
        # Reviewed calibration may only adjust confidence and ordering; zone, path, decoy type and
        # deployment risk are copied through untouched.
        active = calibration or ActiveCalibration()
        placements, change_explanations = apply_calibration(placements, active)
        context_view = _context_view(signals, context, tuple(z.category for z in zones))
        vocab = _vocabulary_view(signals, context)
        confidence: ConfidenceBreakdown = stage(
            "confidence", lambda: compute_confidence(signals, context, zones, placements)
        )
        warnings = stage(
            "warnings",
            lambda: generate_warnings(
                signals, context, zones, placements, ignored_fields, confidence
            ),
        )
        return AnalysisPreviewResponse(
            schema_version=SCHEMA_VERSION,
            organization_id=organization_id,
            request_id=request_id,
            scenario_id=scenario_id,
            input_summary=_input_summary(signals, ignored_fields),
            context_profile=context_view,
            vocabulary=vocab,
            sensitive_zones=zones,
            placement_recommendations=placements,
            warnings=warnings,
            confidence=confidence,
            engine_versions=dict(ENGINE_VERSIONS),
            generated_at=datetime.now(UTC),
            stage_timings_ms=timings,
            calibration=CalibrationAttribution(
                applied=active.active,
                model_version_id=str(active.model_version_id) if active.model_version_id else None,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                organization_specific=active.organization_specific,
                global_aggregate_used=active.global_aggregate_used,
            ),
            change_explanations=change_explanations,
        )


def _input_summary(signals: RepositorySignals, ignored_fields: tuple[str, ...]) -> InputSummary:
    naming = signals.naming_patterns
    naming_count = (
        0
        if naming is None
        else (
            len(naming.entity_names)
            + len(naming.prefixes)
            + len(naming.suffixes)
            + len(naming.environment_terms)
            + len(naming.team_terms)
            + len(naming.domain_terms)
        )
    )
    doc = signals.documentation
    doc_count = (
        0
        if doc is None
        else sum(
            len(g)
            for g in (
                doc.runbook_paths,
                doc.architecture_paths,
                doc.operational_paths,
                doc.support_paths,
                doc.policy_paths,
            )
        )
    )
    recognized = tuple(f for f in KNOWN_TOP_LEVEL_FIELDS if _has_field(signals, f))
    return InputSummary(
        language_count=len(signals.languages),
        framework_count=len(signals.frameworks),
        service_count=len(signals.services),
        database_count=len(signals.databases),
        documentation_signal_count=doc_count,
        secret_location_count=len(signals.secret_locations),
        ai_surface_count=len(signals.ai_surfaces),
        naming_pattern_count=naming_count,
        recognized_categories=tuple(sorted(recognized)),
        ignored_fields=tuple(sorted(ignored_fields)),
    )


def _has_field(signals: RepositorySignals, field: str) -> bool:
    value = getattr(signals, field)
    if value is None:
        return False
    if isinstance(value, tuple):
        return len(value) > 0
    return True
