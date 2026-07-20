// Purpose: pure presentation helpers for the integrations view — status/delivery tones, redacted
//   endpoint display, secret handling, and gating. No network or DOM.
import type { Delivery, IntegrationStatus, IntegrationSummary } from './integrationsTypes';

export function statusTone(status: IntegrationStatus): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'active') return 'success';
  if (status === 'degraded') return 'warning';
  if (status === 'revoked' || status === 'disabled') return 'danger';
  return 'info';
}

export function deliveryTone(status: string): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'delivered') return 'success';
  if (status === 'dead_lettered' || status === 'failed') return 'danger';
  if (status === 'retrying' || status === 'delivering') return 'warning';
  return 'info';
}

// Never render a full endpoint that could contain a token in a query string; show host + path only.
export function redactEndpoint(endpoint: string): string {
  try {
    const url = new URL(endpoint);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch {
    return endpoint.split('?')[0];
  }
}

export function canManage(scopes: readonly string[]): boolean {
  return scopes.includes('integrations:manage');
}

export function canTest(scopes: readonly string[]): boolean {
  return scopes.includes('integrations:test');
}

export function canRetry(scopes: readonly string[]): boolean {
  return scopes.includes('integrations:deliveries:retry');
}

export function canExport(scopes: readonly string[]): boolean {
  return scopes.includes('incidents:export');
}

export function deliverySummary(deliveries: Delivery[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const d of deliveries) out[d.status] = (out[d.status] ?? 0) + 1;
  return out;
}

// Redacted sample payload preview — a bounded, non-sensitive example for the given integration.
export function redactedSamplePayload(integration: IntegrationSummary): string {
  return JSON.stringify(
    {
      schema_version: 'df-security-event-v1',
      event_type: 'deceptiforge.alert.created',
      severity: 'high',
      title: '<redacted sample>',
      source_object_type: 'alert',
      profile: integration.payload_profile,
      note: 'no raw evidence or secrets are ever included',
    },
    null,
    2,
  );
}
