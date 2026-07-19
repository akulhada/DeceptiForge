# Purpose: build the versioned organization browser AI policy document and classify destinations.
# Responsibilities: assemble a bounded, signable policy from the stored record, sign it canonically
#   when signed policies are required, and deterministically classify a destination domain against
#   the policy rules (server-side; the extension's classification is never trusted blindly).
# Dependencies: browser domain, monitor signing, settings.
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.config.settings import Settings
from app.models.domain.browser_sensor import (
    BrowserAiPolicyDoc,
    DestinationClass,
    DomainRule,
    TraceMatchMode,
)
from app.models.records import BrowserAiPolicyRecord
from app.services.monitor_signing import sign

POLICY_SIGNATURE_VERSION = "browser-policy-v1"


def _normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    return d[4:] if d.startswith("www.") else d


def _rules_from_record(record: BrowserAiPolicyRecord) -> tuple[DomainRule, ...]:
    raw = json.loads(record.rules_data or "[]")
    rules: list[DomainRule] = []
    for item in raw:
        rules.append(
            DomainRule(
                domain=_normalize_domain(str(item["domain"])),
                classification=DestinationClass(item["classification"]),
                label=item.get("label"),
            )
        )
    return tuple(rules)


def classify_destination(
    domain: str, rules: tuple[DomainRule, ...]
) -> tuple[DestinationClass, str | None]:
    """Deterministically classify a destination. Longest matching rule domain wins (so a tenant
    subdomain overrides a broader entry). No account identity is inferred."""
    host = _normalize_domain(domain)
    best: DomainRule | None = None
    for rule in rules:
        if host == rule.domain or host.endswith("." + rule.domain):
            if best is None or len(rule.domain) > len(best.domain):
                best = rule
    if best is None:
        return DestinationClass.UNKNOWN, None
    return best.classification, best.label


def _canonical_body(
    *,
    organization_id: str,
    policy_version: int,
    enabled: bool,
    monitored_domains: tuple[str, ...],
    rules: tuple[DomainRule, ...],
    trace_match_mode: TraceMatchMode,
) -> str:
    payload = {
        "v": POLICY_SIGNATURE_VERSION,
        "org": organization_id,
        "policy_version": policy_version,
        "enabled": enabled,
        "monitored_domains": sorted(monitored_domains),
        "rules": sorted(
            ({"domain": r.domain, "classification": r.classification.value} for r in rules),
            key=lambda x: x["domain"],
        ),
        "trace_match_mode": trace_match_mode.value,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def build_policy_doc(
    record: BrowserAiPolicyRecord, settings: Settings, *, signing_secret: str | None = None
) -> BrowserAiPolicyDoc:
    """Assemble the bounded policy document delivered to sensors, optionally signed."""
    rules = _rules_from_record(record)
    # Monitored domains: every rule domain that is not explicitly ignored.
    monitored = tuple(
        sorted({r.domain for r in rules if r.classification != DestinationClass.IGNORED})
    )
    mode = TraceMatchMode(record.trace_match_mode)
    signature: str | None = None
    if settings.browser_sensor_require_signed_policy and signing_secret:
        body = _canonical_body(
            organization_id=str(record.organization_id),
            policy_version=record.policy_version,
            enabled=record.enabled,
            monitored_domains=monitored,
            rules=rules,
            trace_match_mode=mode,
        )
        signature = sign(signing_secret, body)
    return BrowserAiPolicyDoc(
        organization_id=str(record.organization_id),
        enabled=record.enabled,
        monitored_domains=monitored,
        rules=rules,
        trace_match_mode=mode,
        local_only_mode=record.local_only_mode,
        event_reporting_enabled=record.event_reporting_enabled,
        show_user_notification=record.show_user_notification,
        allow_pause=record.allow_pause,
        min_extension_version=record.min_extension_version,
        policy_version=record.policy_version,
        updated_at=record.updated_at or datetime.now(UTC),
        signature=signature,
    )


def policy_body_hash(doc: BrowserAiPolicyDoc) -> str:
    body = _canonical_body(
        organization_id=doc.organization_id,
        policy_version=doc.policy_version,
        enabled=doc.enabled,
        monitored_domains=doc.monitored_domains,
        rules=doc.rules,
        trace_match_mode=doc.trace_match_mode,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
