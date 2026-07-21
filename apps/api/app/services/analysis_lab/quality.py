# Purpose: deterministic confidence breakdown and explainable warnings for a preview analysis.
# Responsibilities: score confidence from signal quantity/diversity/corroboration and penalize for
#   sparsity and contradictions; never report high confidence from repeated identical values.
#   Warnings identify exactly what is missing or conflicting and its effect on interpretation.
# Dependencies: analysis_signals, analysis_preview models, context profile. No I/O.
from __future__ import annotations

from app.models.domain.analysis_preview import (
    AnalysisWarning,
    ConfidenceBreakdown,
    PlacementRecommendationView,
    SensitiveZone,
)
from app.models.domain.analysis_signals import RepositorySignals
from app.models.domain.intelligence import OrganizationContextProfile

# Mutually-distinct business-domain vocabularies; overlap across groups signals a real conflict.
_DOMAIN_GROUPS: dict[str, frozenset[str]] = {
    "fintech": frozenset({"payment", "billing", "ledger", "settlement", "reconciliation", "psp"}),
    "healthcare": frozenset(
        {"patient", "clinical", "provider", "claims", "hl7", "phi", "scheduling"}
    ),
    "ecommerce": frozenset({"catalog", "order", "cart", "checkout", "fulfillment", "inventory"}),
    "saas_crm": frozenset({"tenant", "subscription", "account", "crm", "seat", "workspace"}),
    "ml_data": frozenset({"embedding", "vector", "model", "pipeline", "feature", "retrieval"}),
}


def _present_categories(signals: RepositorySignals) -> tuple[str, ...]:
    cats: list[str] = []
    if signals.languages:
        cats.append("languages")
    if signals.frameworks:
        cats.append("frameworks")
    if signals.package_managers:
        cats.append("package_managers")
    if signals.services:
        cats.append("services")
    if signals.databases:
        cats.append("databases")
    if signals.documentation is not None:
        cats.append("documentation")
    if signals.secret_locations:
        cats.append("secret_locations")
    if signals.ai_surfaces:
        cats.append("ai_surfaces")
    if signals.naming_patterns is not None:
        cats.append("naming_patterns")
    if signals.infrastructure is not None:
        cats.append("infrastructure")
    return tuple(cats)


def _domain_terms(signals: RepositorySignals) -> set[str]:
    terms: set[str] = set()
    if signals.naming_patterns is not None:
        for t in (*signals.naming_patterns.domain_terms, *signals.naming_patterns.entity_names):
            terms.add(t.lower())
    for s in signals.services:
        terms.add(s.name.lower())
    for db in signals.databases:
        for t in db.data_domain_terms:
            terms.add(t.lower())
    return terms


def domain_conflict_score(signals: RepositorySignals) -> tuple[float, tuple[str, ...]]:
    """0 = no conflict, up to 1 = strong contradiction. Returns (score, conflicting groups)."""
    terms = _domain_terms(signals)
    hits = [g for g, vocab in _DOMAIN_GROUPS.items() if terms & vocab]
    if len(hits) <= 1:
        return 0.0, ()
    # Two or more distinct domains present -> conflict grows with the number of colliding domains.
    return round(min(1.0, 0.4 + 0.2 * (len(hits) - 1)), 4), tuple(sorted(hits))


def _mean(values: tuple[float, ...]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def compute_confidence(
    signals: RepositorySignals,
    context: OrganizationContextProfile,
    zones: tuple[SensitiveZone, ...],
    placements: tuple[PlacementRecommendationView, ...],
) -> ConfidenceBreakdown:
    present = _present_categories(signals)
    completeness = round(len(present) / 10, 4)
    conflict, _ = domain_conflict_score(signals)
    # Vocabulary confidence rewards DISTINCT terms, not repeated values.
    distinct_terms = len(_domain_terms(signals))
    vocabulary = round(min(1.0, 0.15 + 0.06 * distinct_terms), 4)
    domain = round(max(0.0, context.confidence * (1 - 0.5 * conflict)), 4)
    sensitive = _mean(tuple(z.confidence for z in zones[:5]))
    placement = _mean(tuple(p.confidence for p in placements[:5]))
    # Overall: diversity-weighted, penalized by sparsity and conflict; capped so repetition alone
    # cannot manufacture certainty.
    overall = round(
        max(
            0.0,
            (
                0.3 * domain
                + 0.2 * vocabulary
                + 0.2 * sensitive
                + 0.15 * placement
                + 0.15 * completeness
            )
            * (1 - 0.4 * conflict),
        ),
        4,
    )
    return ConfidenceBreakdown(
        overall=min(overall, 1.0),
        domain=domain,
        vocabulary=vocabulary,
        sensitive_zone=sensitive,
        placement=placement,
        completeness=completeness,
        conflict=conflict,
    )


def generate_warnings(
    signals: RepositorySignals,
    context: OrganizationContextProfile,
    zones: tuple[SensitiveZone, ...],
    placements: tuple[PlacementRecommendationView, ...],
    ignored_fields: tuple[str, ...],
    confidence: ConfidenceBreakdown,
) -> tuple[AnalysisWarning, ...]:
    present = set(_present_categories(signals))
    warnings: list[AnalysisWarning] = []

    def warn(code: str, message: str, effect: str) -> None:
        warnings.append(AnalysisWarning(code=code, message=message, effect=effect))

    if len(present) <= 2:
        warn(
            "sparse_input",
            f"Only {len(present)} signal categories provided.",
            "Domain and placement inference are low-confidence and may be omitted.",
        )
    if not _domain_terms(signals):
        warn(
            "no_business_domain",
            "No business-domain vocabulary (domain/entity terms) provided.",
            "Business domain is not inferred; no domain is fabricated.",
        )
    if signals.documentation is None:
        warn(
            "no_documentation",
            "No documentation signals provided.",
            "Operational maturity and doc-based placement zones are weaker.",
        )
    if signals.infrastructure is None:
        warn(
            "no_infrastructure",
            "No infrastructure signals provided.",
            "Deployment and infrastructure sensitivity cannot be corroborated.",
        )
    if not zones:
        warn(
            "no_sensitive_zones",
            "No plausible sensitive zones matched.",
            "No placement recommendations are anchored to a sensitive category.",
        )
    conflict_score, groups = domain_conflict_score(signals)
    if conflict_score > 0:
        warn(
            "conflicting_business_domain",
            f"Conflicting domain vocabulary across {', '.join(groups)}.",
            "Domain confidence is reduced and placement is kept conservative.",
        )
    poorly_classified = [s for s in signals.secret_locations if not s.category]
    if poorly_classified:
        warn(
            "secrets_poorly_classified",
            f"{len(poorly_classified)} secret location(s) lack a category.",
            "Secret-zone ranking relies on path text only; classify for stronger evidence.",
        )
    services = {s.name.lower() for s in signals.services}
    if signals.ai_surfaces and not services:
        warn(
            "ai_surface_without_service_context",
            "AI surfaces present without any service context.",
            "AI-exposure inference lacks corroboration from a hosting service.",
        )
    weak = [p for p in placements if p.confidence < 0.4]
    if weak:
        warn(
            "weak_evidence_recommendations",
            f"{len(weak)} recommendation(s) rest on weak evidence (confidence < 0.4).",
            "Treat those placements as exploratory, not deployment-ready.",
        )
    if ignored_fields:
        warn(
            "unknown_fields_ignored",
            f"Ignored unknown fields: {', '.join(ignored_fields)}.",
            "Those keys did not influence the analysis.",
        )
    if confidence.overall < 0.35:
        warn(
            "low_overall_confidence",
            "Overall confidence is below 0.35.",
            "Interpret the whole result as directional, not definitive.",
        )
    return tuple(warnings)
