// Purpose: verify browser-sensor admin gating, staleness, tone, and exposure labels.
import { describe, expect, it } from 'vitest';

import {
  availableActions,
  classificationTone,
  exposureLabel,
  isStale,
  statusTone,
} from './browserSensorPermissions';
import type { BrowserEvent, SensorSummary } from './browserSensorTypes';

const MANAGE = ['browser_sensors:read', 'browser_sensors:manage'];

function sensor(over: Partial<SensorSummary>): SensorSummary {
  return {
    id: 's',
    sensor_public_id: 'dfs_1',
    name: 'laptop',
    device_label: null,
    browser_family: 'chromium',
    extension_version: '0.1.0',
    status: 'active',
    last_seen_at: new Date().toISOString(),
    created_at: '',
    ...over,
  };
}

describe('availableActions', () => {
  it('offers revoke+rotate to managers on non-revoked sensors', () => {
    expect(availableActions('active', MANAGE)).toEqual(['rotate', 'revoke']);
    expect(availableActions('active', ['browser_sensors:read'])).toEqual([]);
    expect(availableActions('revoked', MANAGE)).toEqual([]);
  });
});

describe('isStale', () => {
  it('flags an active sensor unseen for over a day', () => {
    const old = new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString();
    expect(isStale(sensor({ last_seen_at: old }))).toBe(true);
    expect(isStale(sensor({ last_seen_at: new Date().toISOString() }))).toBe(false);
    expect(isStale(sensor({ status: 'active', last_seen_at: null }))).toBe(true);
    // Revoked sensors are not "stale".
    expect(isStale(sensor({ status: 'revoked', last_seen_at: null }))).toBe(false);
  });
});

describe('tones and labels', () => {
  it('maps status and classification to tones', () => {
    expect(statusTone('active')).toBe('success');
    expect(statusTone('revoked')).toBe('danger');
    expect(classificationTone('shadow')).toBe('danger');
    expect(classificationTone('approved')).toBe('success');
  });

  it('labels events', () => {
    const base: BrowserEvent = {
      id: 'e',
      browser_sensor_id: 's',
      trace_id: 'DFAI-abc',
      destination_domain: 'chatgpt.com',
      destination_classification: 'shadow',
      event_type: 'shadow_ai_paste_detected',
      match_method: 'exact',
      confidence: 1,
      extension_version: '0.1.0',
      policy_version: 1,
      minimized_metadata: '{}',
      correlation_id: 'c',
      observed_at: '2026-07-19T00:00:00',
    };
    expect(exposureLabel(base)).toBe('Shadow AI exposure');
    expect(exposureLabel({ ...base, event_type: 'approved_ai_paste_detected' })).toBe(
      'Approved AI paste',
    );
    expect(exposureLabel({ ...base, event_type: 'unknown_future' })).toBe('AI paste exposure');
  });
});
