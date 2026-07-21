# Purpose: deterministic, stable ranking of sensitive zones from structured signals.
# Responsibilities: pool descriptive evidence (service names, vocabulary, doc/secret/AI signals),
#   match against a fixed category keyword table, and produce risk-ranked zones with explanations.
#   Stable for identical input; repeated identical evidence does not inflate scores (deduped).
# Dependencies: analysis_signals contract, analysis_preview response models. No I/O.
from __future__ import annotations

from app.models.domain.analysis_preview import SensitiveZone
from app.models.domain.analysis_signals import RepositorySignals

# category -> (keywords, base_risk, decoy_types). Order of table is the deterministic tie-breaker.
_CATEGORIES: tuple[tuple[str, tuple[str, ...], float, tuple[str, ...]], ...] = (
    (
        "secrets_and_credentials",
        ("secret", "credential", "token", "apikey", "api_key", "vault", "password", "key"),
        0.95,
        ("secret", "environment_file"),
    ),
    (
        "payment",
        ("payment", "card", "charge", "settlement", "acquirer", "psp", "stripe"),
        0.9,
        ("secret", "config_file", "document"),
    ),
    (
        "billing",
        ("billing", "invoice", "reconciliation", "ledger", "subscription", "pricing"),
        0.82,
        ("document", "spreadsheet_row"),
    ),
    (
        "authentication",
        ("auth", "login", "session", "oauth", "sso", "jwt", "identity"),
        0.85,
        ("secret", "config_file"),
    ),
    (
        "authorization",
        ("authorization", "rbac", "permission", "scope", "policy", "role"),
        0.75,
        ("config_file", "document"),
    ),
    (
        "customer_data",
        (
            "customer",
            "account",
            "tenant",
            "user",
            "profile",
            "crm",
            "pii",
            "patient",
            "member",
            "subscriber",
            "provider",
        ),
        0.8,
        ("database_record", "spreadsheet_row"),
    ),
    (
        "ai_or_rag_systems",
        ("rag", "embedding", "vector", "retrieval", "llm", "prompt", "mcp", "model", "inference"),
        0.78,
        ("mcp_config", "rag_document"),
    ),
    (
        "data_pipelines",
        ("pipeline", "etl", "ingest", "warehouse", "feature", "dataset", "airflow"),
        0.7,
        ("document", "config_file"),
    ),
    (
        "deployment",
        ("deploy", "release", "rollout", "helm", "kustomize", "argocd", "pipeline"),
        0.72,
        ("ci_cd_file", "config_file"),
    ),
    (
        "infrastructure",
        ("kubernetes", "k8s", "terraform", "docker", "cluster", "network", "cloud"),
        0.68,
        ("config_file", "ci_cd_file"),
    ),
    (
        "support_operations",
        ("support", "helpdesk", "ticket", "escalation", "oncall", "runbook"),
        0.6,
        ("document", "internal_wiki_page"),
    ),
    (
        "incident_response",
        ("incident", "postmortem", "sev", "outage", "pager"),
        0.62,
        ("document", "internal_wiki_page"),
    ),
    (
        "administration",
        ("admin", "superuser", "backoffice", "console", "management"),
        0.7,
        ("config_file", "document"),
    ),
    (
        "compliance_documentation",
        ("compliance", "hipaa", "pci", "gdpr", "soc2", "audit", "policy"),
        0.6,
        ("document", "policy"),
    ),
)


def _pool(signals: RepositorySignals) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    """Return (category-hit paths per token source) and a deduped lowercase evidence-term set."""
    terms: set[str] = set()
    representative: list[str] = []

    def add(*values: str | None) -> None:
        for v in values:
            if v:
                terms.add(v.lower())

    for svc in signals.services:
        add(svc.name, svc.service_type)
        representative.extend(svc.representative_paths)
    for fw in signals.frameworks:
        add(fw.name, fw.category)
    for lang in signals.languages:
        add(lang.name)
    for db in signals.databases:
        add(db.engine, db.usage, *db.data_domain_terms)
        representative.extend(db.schema_or_migration_paths)
    for secret in signals.secret_locations:
        add(secret.path, secret.category, secret.source_type)
        representative.append(secret.path)
    for ai in signals.ai_surfaces:
        add(ai.surface_type, ai.provider_or_framework, ai.path_or_resource)
    if signals.naming_patterns is not None:
        n = signals.naming_patterns
        for group in (n.domain_terms, n.entity_names, n.team_terms, n.environment_terms):
            for t in group:
                add(t)
    if signals.documentation is not None:
        d = signals.documentation
        for group in (
            d.runbook_paths,
            d.architecture_paths,
            d.operational_paths,
            d.support_paths,
            d.policy_paths,
        ):
            representative.extend(group)
            for p in group:
                add(p)
    if signals.infrastructure is not None:
        i = signals.infrastructure
        for group in (
            i.container_tools,
            i.orchestration,
            i.cloud_indicators,
            i.ci_cd,
            i.infrastructure_as_code,
            i.deployment_paths,
        ):
            for t in group:
                add(t)
    return {"paths": tuple(representative)}, terms


def rank_sensitive_zones(
    signals: RepositorySignals, *, limit: int = 12
) -> tuple[SensitiveZone, ...]:
    pooled, terms = _pool(signals)
    haystack = " ".join(sorted(terms)) + " " + " ".join(p.lower() for p in pooled["paths"])
    zones: list[SensitiveZone] = []
    for category, keywords, base_risk, decoy_types in _CATEGORIES:
        matched = sorted({kw for kw in keywords if kw in haystack})
        if not matched:
            continue
        # Distinct-keyword coverage drives score, so repeated identical evidence cannot inflate it.
        coverage = len(matched) / len(keywords)
        risk = round(base_risk * (0.55 + 0.45 * coverage), 4)
        confidence = round(min(1.0, 0.35 + 0.2 * len(matched)), 4)
        paths = tuple(p for p in pooled["paths"] if any(kw in p.lower() for kw in matched))[:8]
        warnings: list[str] = []
        if category == "secrets_and_credentials":
            warnings.append(
                "Descriptive metadata only — never deploy a decoy inside a real secret."
            )
        if len(matched) == 1:
            warnings.append("Single-keyword evidence; treat ranking as weak.")
        zones.append(
            SensitiveZone(
                zone_id=f"zone_{category}",
                category=category,
                representative_paths=paths,
                risk_score=risk,
                confidence=confidence,
                supporting_signals=tuple(matched)[:20],
                reasoning=(
                    f"{category.replace('_', ' ').title()} evidence matched "
                    f"{len(matched)} of {len(keywords)} indicators ({', '.join(matched[:6])})."
                ),
                relevant_decoy_types=decoy_types,
                warnings=tuple(warnings),
            )
        )
    # Deterministic order: risk desc, then confidence desc, then category asc (table-stable).
    zones.sort(key=lambda z: (-z.risk_score, -z.confidence, z.category))
    return tuple(zones[:limit])
