// Purpose: pure presentation helpers for the reliability view — dependency/backup age tones,
//   RPO/RTO within-target checks, and failover gating. No network or DOM.
import type { DependencyStatus, LatestRestore, ReliabilityStatus } from './reliabilityTypes';

export function dependencyTone(status: string): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'ok' || status === 'not_required') return 'success';
  if (status === 'unavailable') return 'danger';
  return 'warning';
}

export function isDegraded(deps: DependencyStatus): boolean {
  return (
    deps.database.status !== 'ok' ||
    deps.encryption.status !== 'ok' ||
    (deps.replay_protection.required && deps.replay_protection.status !== 'ok')
  );
}

// A restore is stale if the latest verified restore is older than the drill cadence (7 days).
export function restoreIsStale(latest: LatestRestore | null, now: number = Date.now()): boolean {
  if (!latest) return true;
  return now - Date.parse(latest.created_at) > 7 * 24 * 60 * 60 * 1000;
}

export function withinCriticalTargets(status: ReliabilityStatus): boolean {
  const latest = status.latest_verified_restore;
  const critical = status.recovery_objectives['critical'];
  if (!latest || !critical || latest.achieved_rpo_minutes === null || latest.achieved_rto_minutes === null) {
    return false;
  }
  return (
    latest.achieved_rpo_minutes <= critical.rpo_minutes &&
    latest.achieved_rto_minutes <= critical.rto_minutes
  );
}

export function canRequestFailover(scopes: readonly string[]): boolean {
  return scopes.includes('failover:request');
}

export function canApproveFailover(scopes: readonly string[]): boolean {
  return scopes.includes('failover:approve');
}

export function failoverTone(state: string): 'info' | 'success' | 'warning' | 'danger' {
  if (state === 'normal' || state === 'normal_restored') return 'success';
  if (state === 'secondary_active' || state === 'degraded') return 'warning';
  return 'danger';
}
