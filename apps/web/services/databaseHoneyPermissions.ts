// Purpose: decide which honey-deployment actions a viewer may take, given status and scopes.
// Responsibilities: pure mapping used by the dashboard to show only permitted actions and warn on
//   drift. No network or DOM. Dependencies: honey types.
import type { HoneyStatus, HoneyDeploymentSummary } from './databaseHoneyTypes';

export type HoneyAction = 'submit' | 'approve' | 'reject' | 'deploy' | 'retire' | 'rollback';

const REQUIRED_SCOPE: Record<HoneyAction, string> = {
  submit: 'database_honey:create',
  approve: 'database_honey:approve',
  reject: 'database_honey:approve',
  deploy: 'database_honey:deploy',
  retire: 'database_honey:retire',
  rollback: 'database_honey:rollback',
};

const ACTIONS_FOR_STATUS: Partial<Record<HoneyStatus, readonly HoneyAction[]>> = {
  draft: ['submit'],
  awaiting_approval: ['approve', 'reject'],
  approved: ['deploy'],
  failed: ['submit'],
  deployed: ['retire', 'rollback'],
  deployed_unmonitored: ['retire', 'rollback'],
  verification_failed: ['rollback'],
  failed_activation: ['rollback'],
  drift_detected: ['retire', 'rollback'],
};

export function availableActions(
  status: HoneyStatus,
  scopes: readonly string[],
): readonly HoneyAction[] {
  const scopeSet = new Set(scopes);
  return (ACTIONS_FOR_STATUS[status] ?? []).filter((action) => scopeSet.has(REQUIRED_SCOPE[action]));
}

export function isDrift(status: HoneyStatus): boolean {
  return status === 'drift_detected';
}

export function monitoringLabel(summary: HoneyDeploymentSummary): string {
  if (summary.monitoring_activated) return 'Active';
  if (summary.status === 'deployed_unmonitored' || summary.status === 'failed_activation') {
    return 'Activation failed';
  }
  return 'Not activated';
}

export function isTerminal(status: HoneyStatus): boolean {
  return (
    status === 'rejected' ||
    status === 'cancelled' ||
    status === 'retired' ||
    status === 'rolled_back'
  );
}
