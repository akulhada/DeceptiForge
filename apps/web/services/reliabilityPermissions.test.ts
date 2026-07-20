// Purpose: verify reliability presentation helpers — dependency tone, degraded detection, restore
//   staleness, RPO/RTO target check, failover gating + tone.
import { describe, expect, it } from 'vitest';

import {
  canApproveFailover,
  canRequestFailover,
  dependencyTone,
  failoverTone,
  isDegraded,
  restoreIsStale,
  withinCriticalTargets,
} from './reliabilityPermissions';
import type { DependencyStatus, ReliabilityStatus } from './reliabilityTypes';

function deps(over: Partial<DependencyStatus>): DependencyStatus {
  return {
    database: { status: 'ok' },
    redis: { status: 'ok' },
    encryption: { status: 'ok' },
    replay_protection: { required: false, status: 'ok' },
    active_region: { role: 'primary', is_active_write_region: true, epoch: 1 },
    maintenance_mode: false,
    ...over,
  };
}

describe('dependencyTone + isDegraded', () => {
  it('maps status and flags degraded', () => {
    expect(dependencyTone('ok')).toBe('success');
    expect(dependencyTone('not_required')).toBe('success');
    expect(dependencyTone('unavailable')).toBe('danger');
    expect(isDegraded(deps({}))).toBe(false);
    expect(isDegraded(deps({ database: { status: 'unavailable' } }))).toBe(true);
    expect(
      isDegraded(deps({ replay_protection: { required: true, status: 'unavailable' } })),
    ).toBe(true);
  });
});

describe('restoreIsStale + withinCriticalTargets', () => {
  const base: ReliabilityStatus = {
    region: {
      deployment_region: 'r', cluster_id: 'c', environment: 'production', role: 'primary',
      deployment_revision: 'x', database_cluster_id: 'd', active_region_epoch: 1,
      secondary_region: null, dr_enabled: false, maintenance_mode: false,
    },
    failover_state: 'normal',
    recovery_objectives: {
      critical: { data_class: 'critical', rpo_minutes: 5, rto_minutes: 60, recomputable: false },
    },
    latest_verified_restore: {
      backup_identifier: 'b', passed: true, achieved_rpo_minutes: 2, achieved_rto_minutes: 30,
      created_at: new Date().toISOString(),
    },
    maintenance_mode: false,
  };

  it('flags a missing or old restore as stale', () => {
    expect(restoreIsStale(null)).toBe(true);
    const old = new Date(Date.now() - 10 * 24 * 3600 * 1000).toISOString();
    expect(restoreIsStale({ ...base.latest_verified_restore!, created_at: old })).toBe(true);
    expect(restoreIsStale(base.latest_verified_restore)).toBe(false);
  });

  it('checks RPO/RTO against critical targets', () => {
    expect(withinCriticalTargets(base)).toBe(true);
    const over = {
      ...base,
      latest_verified_restore: { ...base.latest_verified_restore!, achieved_rpo_minutes: 9 },
    };
    expect(withinCriticalTargets(over)).toBe(false);
    expect(withinCriticalTargets({ ...base, latest_verified_restore: null })).toBe(false);
  });
});

describe('failover gating + tone', () => {
  it('gates and tones', () => {
    expect(canRequestFailover(['failover:request'])).toBe(true);
    expect(canApproveFailover(['failover:approve'])).toBe(true);
    expect(canRequestFailover(['reliability:read'])).toBe(false);
    expect(failoverTone('normal')).toBe('success');
    expect(failoverTone('primary_fenced')).toBe('danger');
    expect(failoverTone('degraded')).toBe('warning');
  });
});
