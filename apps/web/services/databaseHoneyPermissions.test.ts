// Purpose: verify honey-deployment action gating, drift detection, and monitoring labels.
import { describe, expect, it } from 'vitest';

import {
  availableActions,
  isDrift,
  isTerminal,
  monitoringLabel,
} from './databaseHoneyPermissions';
import type { HoneyDeploymentSummary } from './databaseHoneyTypes';

const ALL = [
  'database_honey:read',
  'database_honey:create',
  'database_honey:approve',
  'database_honey:deploy',
  'database_honey:retire',
  'database_honey:rollback',
];

describe('availableActions', () => {
  it('gates submit/approve/deploy by status and scope', () => {
    expect(availableActions('draft', ['database_honey:create'])).toEqual(['submit']);
    expect(availableActions('draft', ['database_honey:read'])).toEqual([]);
    expect(availableActions('awaiting_approval', ['database_honey:approve'])).toEqual([
      'approve',
      'reject',
    ]);
    expect(availableActions('approved', ['database_honey:deploy'])).toEqual(['deploy']);
  });

  it('offers retire and rollback on deployed and drift', () => {
    expect(availableActions('deployed', ALL)).toEqual(['retire', 'rollback']);
    expect(availableActions('drift_detected', ALL)).toEqual(['retire', 'rollback']);
    expect(availableActions('verification_failed', ALL)).toEqual(['rollback']);
  });

  it('offers no actions on terminal states', () => {
    for (const status of ['retired', 'rolled_back', 'rejected', 'cancelled'] as const) {
      expect(availableActions(status, ALL)).toEqual([]);
      expect(isTerminal(status)).toBe(true);
    }
  });
});

describe('isDrift', () => {
  it('flags drift_detected', () => {
    expect(isDrift('drift_detected')).toBe(true);
    expect(isDrift('deployed')).toBe(false);
  });
});

describe('monitoringLabel', () => {
  const base: HoneyDeploymentSummary = {
    id: 'd',
    connector_id: 'c',
    target_schema: 'public',
    target_table: 'customers',
    decoy_type: 'synthetic_customer',
    status: 'deployed',
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
