// Purpose: decide which deployment lifecycle actions a viewer may take, given status and scopes.
// Responsibilities: pure, side-effect-free mapping used by the dashboard to show only permitted
//   actions and to warn on stale previews. No network or DOM. Dependencies: deployment types.
import type { DeploymentStatus, DeploymentSummary } from './deploymentTypes';

export type DeploymentAction =
  | 'submit'
  | 'approve'
  | 'reject'
  | 'deploy'
  | 'retire'
  | 'rollback';

const REQUIRED_SCOPE: Record<DeploymentAction, string> = {
  submit: 'decoy_deployments:create',
  approve: 'decoy_deployments:approve',
  reject: 'decoy_deployments:approve',
  deploy: 'decoy_deployments:execute',
  retire: 'decoy_deployments:retire',
  rollback: 'decoy_deployments:rollback',
};

// Which actions the current status allows (before permission filtering).
const ACTIONS_FOR_STATUS: Partial<Record<DeploymentStatus, readonly DeploymentAction[]>> = {
  draft: ['submit'],
  awaiting_approval: ['approve', 'reject'],
  reapproval_required: ['submit'],
  approved: ['deploy'],
  failed: ['submit'],
  deployed: ['retire', 'rollback'],
  deployed_unmonitored: ['retire', 'rollback'],
  verification_failed: ['rollback'],
  failed_activation: ['rollback'],
};

export function availableActions(
  status: DeploymentStatus,
  scopes: readonly string[],
): readonly DeploymentAction[] {
  const scopeSet = new Set(scopes);
  return (ACTIONS_FOR_STATUS[status] ?? []).filter((action) =>
    scopeSet.has(REQUIRED_SCOPE[action]),
  );
}

export function canPerform(
  action: DeploymentAction,
  status: DeploymentStatus,
  scopes: readonly string[],
): boolean {
  return availableActions(status, scopes).includes(action);
}

export function isPreviewStale(status: DeploymentStatus): boolean {
  return status === 'preview_stale' || status === 'reapproval_required';
}

export function monitoringLabel(summary: DeploymentSummary): string {
  if (summary.monitoring_activated) return 'Active';
  if (summary.status === 'deployed_unmonitored' || summary.status === 'failed_activation') {
    return 'Activation failed';
  }
  return 'Not activated';
}

export function isTerminal(status: DeploymentStatus): boolean {
  return (
    status === 'rejected' ||
    status === 'cancelled' ||
    status === 'retired' ||
    status === 'rolled_back'
  );
}
