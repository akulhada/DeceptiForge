// Purpose: local destination classification for display and pre-filtering.
// Responsibilities: normalize a host and classify it against the policy rules (longest match wins).
//   The backend re-classifies authoritatively on ingest; this is presentation/pre-filter only.
import type { DestinationClass, DomainRule } from './types';

export function normalizeDomain(domain: string): string {
  const d = domain.trim().toLowerCase();
  return d.startsWith('www.') ? d.slice(4) : d;
}

export function classifyDestination(host: string, rules: DomainRule[]): DestinationClass {
  const h = normalizeDomain(host);
  let best: DomainRule | null = null;
  for (const rule of rules) {
    const rd = normalizeDomain(rule.domain);
    if (h === rd || h.endsWith('.' + rd)) {
      if (best === null || rd.length > normalizeDomain(best.domain).length) best = rule;
    }
  }
  return best ? best.classification : 'unknown';
}

export function isMonitored(host: string, monitoredDomains: string[]): boolean {
  const h = normalizeDomain(host);
  return monitoredDomains.some((d) => {
    const rd = normalizeDomain(d);
    return h === rd || h.endsWith('.' + rd);
  });
}

export function eventTypeFor(classification: DestinationClass): string {
  if (classification === 'approved') return 'approved_ai_paste_detected';
  if (classification === 'shadow' || classification === 'unknown') {
    return 'shadow_ai_paste_detected';
  }
  return 'ai_paste_trace_detected';
}
