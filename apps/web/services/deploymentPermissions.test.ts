// Purpose: verify deployment action gating, stale-preview detection, and monitoring labels.
import { describe, expect, it } from 'vitest';

import {
  availableActions,
  canPerform,
  isPreviewStale,
  isTerminal,
  monitoringLabel,
} from './deploymentPermissions';
import type { DeploymentSummary } from './deploymentTypes';

const ALL = [
  'decoy_deployments:read',
  'decoy_deployments:create',
  'decoy_deployments:approve',
  'decoy_deployments:execute',
  'decoy_deployments:retire',
  'decoy_deployments:rollback',
];

describe('availableActions', () => {
  it('offers submit on draft only with create scope', () => {
    expect(availableActions('draft', ['decoy_deployments:create'])).toEqual(['submit']);
    expect(availableActions('draft', ['decoy_deployments:read'])).toEqual([]);
  });

  it('offers approve/reject on awaiting_approval only with approve scope', () => {
    expect(availableActions('awaiting_approval', ['decoy_deployments:approve'])).toEqual([
      'approve',
      'reject',
    ]);
    expect(availableActions('awaiting_approval', ['decoy_deployments:read'])).toEqual([]);
  });

  it('offers deploy only when approved and with execute scope', () => {
    expect(canPerform('deploy', 'approved', ['decoy_deployments:execute'])).toBe(true);
    expect(canPerform('deploy', 'awaiting_approval', ALL)).toBe(false);
  });

  it('offers retire and rollback on a deployed deployment', () => {
    expect(availableActions('deployed', ALL)).toEqual(['retire', 'rollback']);
  });

  it('offers rollback (not retire) after verification/activation failure', () => {
    expect(availableActions('verification_failed', ALL)).toEqual(['rollback']);
    expect(availableActions('failed_activation', ALL)).toEqual(['rollback']);
  });

  it('offers no actions on terminal states', () => {
    for (const status of ['retired', 'rolled_back', 'rejected', 'cancelled'] as const) {
      expect(availableActions(status, ALL)).toEqual([]);
      expect(isTerminal(status)).toBe(true);
    }
  });
});

describe('isPreviewStale', () => {
  it('flags stale and reapproval-required states', () => {
    expect(isPreviewStale('preview_stale')).toBe(true);
    expect(isPreviewStale('reapproval_required')).toBe(true);
    expect(isPreviewStale('deployed')).toBe(false);
  });
});

describe('monitoringLabel', () => {
  const base: DeploymentSummary = {
    id: 'd',
    repository_id: 'r',
    decoy_plan_id: 'p',
    status: 'deployed',
    target_branch: 'main',
    base_commit_sha: 'x',
    pull_request_number: 1,
    pull_request_url: 'https://example.invalid/pull/1',
    monitoring_activated: true,
    expires_at: null,
    failure_code: null,
    safe_failure_message: null,
    created_at: '',
    updated_at: '',
  };

  it('labels active vs failed vs not activated', () => {
    expect(monitoringLabel(base)).toBe('Active');
    expect(monitoringLabel({ ...base, monitoring_activated: false })).toBe('Not activated');
    expect(
      monitoringLabel({ ...base, monitoring_activated: false, status: 'deployed_unmonitored' }),
    ).toBe('Activation failed');
  });
});
