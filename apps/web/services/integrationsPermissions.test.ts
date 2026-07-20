// Purpose: verify integrations presentation helpers — tones, endpoint redaction (no query token),
//   gating, delivery summary, redacted sample payload has no secrets.
import { describe, expect, it } from 'vitest';

import {
  canExport,
  canManage,
  canRetry,
  canTest,
  deliverySummary,
  deliveryTone,
  redactEndpoint,
  redactedSamplePayload,
  statusTone,
} from './integrationsPermissions';
import type { Delivery, IntegrationSummary } from './integrationsTypes';

describe('tones', () => {
  it('maps integration + delivery status', () => {
    expect(statusTone('active')).toBe('success');
    expect(statusTone('degraded')).toBe('warning');
    expect(statusTone('revoked')).toBe('danger');
    expect(deliveryTone('delivered')).toBe('success');
    expect(deliveryTone('dead_lettered')).toBe('danger');
    expect(deliveryTone('retrying')).toBe('warning');
  });
});

describe('redactEndpoint', () => {
  it('strips query strings that could carry a token', () => {
    expect(redactEndpoint('https://siem.example.com/hook?token=SECRET')).toBe(
      'https://siem.example.com/hook',
    );
    expect(redactEndpoint('not a url?token=x')).toBe('not a url');
  });
});

describe('gating', () => {
  it('checks scopes', () => {
    expect(canManage(['integrations:manage'])).toBe(true);
    expect(canManage(['integrations:read'])).toBe(false);
    expect(canTest(['integrations:test'])).toBe(true);
    expect(canRetry(['integrations:deliveries:retry'])).toBe(true);
    expect(canExport(['incidents:export'])).toBe(true);
  });
});

describe('deliverySummary + sample payload', () => {
  it('counts by status', () => {
    const deliveries = [
      { status: 'delivered' }, { status: 'delivered' }, { status: 'dead_lettered' },
    ] as Delivery[];
    expect(deliverySummary(deliveries)).toEqual({ delivered: 2, dead_lettered: 1 });
  });

  it('sample payload has no secrets and notes minimization', () => {
    const integration = { payload_profile: 'standard' } as IntegrationSummary;
    const sample = redactedSamplePayload(integration);
    expect(sample).toContain('no raw evidence or secrets');
    expect(sample.toLowerCase()).not.toContain('token=');
  });
});
