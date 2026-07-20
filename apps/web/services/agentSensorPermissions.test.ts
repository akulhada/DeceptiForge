// Purpose: verify agent-sensor admin helpers — staleness, tones, decoy-touch, labels, gating.
import { describe, expect, it } from 'vitest';

import {
  canManagePolicies,
  canManageSensors,
  isDecoyTouch,
  isStale,
  pathClassTone,
  severityTone,
  statusTone,
  violationLabel,
} from './agentSensorPermissions';
import type { AgentSensorSummary, AgentTimelineEvent, AgentViolation } from './agentSensorTypes';

function sensor(over: Partial<AgentSensorSummary>): AgentSensorSummary {
  return {
    id: 's', sensor_public_id: 'dfa_1', name: 'cli', adapter_type: 'jsonl', version: '0.1.0',
    status: 'active', last_seen_at: new Date().toISOString(), created_at: '', ...over,
  };
}

describe('isStale', () => {
  it('flags active sensors unseen for over a day', () => {
    const old = new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString();
    expect(isStale(sensor({ last_seen_at: old }))).toBe(true);
    expect(isStale(sensor({ last_seen_at: null }))).toBe(true);
    expect(isStale(sensor({}))).toBe(false);
    expect(isStale(sensor({ status: 'revoked', last_seen_at: null }))).toBe(false);
  });
});

describe('tones', () => {
  it('maps status, path class, severity', () => {
    expect(statusTone('active')).toBe('success');
    expect(statusTone('revoked')).toBe('danger');
    expect(pathClassTone('decoy')).toBe('danger');
    expect(pathClassTone('credential')).toBe('warning');
    expect(pathClassTone('task_relevant')).toBe('success');
    expect(severityTone('high')).toBe('danger');
    expect(severityTone('medium')).toBe('warning');
    expect(severityTone('info')).toBe('info');
  });
});

describe('isDecoyTouch', () => {
  const base: AgentTimelineEvent = {
    id: 'e', event_type: 'file_read', normalized_path: 'a.ts', path_class: 'task_relevant',
    tool_name: null, resource_type: null, decoy_id: null, trace_id: null, result_status: 'ok',
    minimized_metadata: '{}', observed_at: '2026-07-19T00:00:00',
  };
  it('detects decoy id or decoy path class', () => {
    expect(isDecoyTouch(base)).toBe(false);
    expect(isDecoyTouch({ ...base, decoy_id: 'd1' })).toBe(true);
    expect(isDecoyTouch({ ...base, path_class: 'decoy' })).toBe(true);
  });
});

describe('violationLabel + gating', () => {
  it('humanizes and gates', () => {
    const v: AgentViolation = {
      id: 'v', event_id: 'e', violation_type: 'sensitive_file_access', severity: 'medium',
      confidence: 0.85, policy_rule: 'sensitive_over_cap', explanation: 'x', created_at: '',
    };
    expect(violationLabel(v)).toBe('sensitive file access');
    expect(canManageSensors(['agent_sensors:manage'])).toBe(true);
    expect(canManageSensors(['agent_sensors:read'])).toBe(false);
    expect(canManagePolicies(['agent_policies:manage'])).toBe(true);
  });
});
