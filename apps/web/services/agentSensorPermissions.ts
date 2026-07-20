// Purpose: pure helpers for the agent-sensor admin view — status tone, staleness, path-class and
//   violation/severity tones, and exposure labels. No network or DOM.
import type {
  AgentSensorStatus,
  AgentSensorSummary,
  AgentTimelineEvent,
  AgentViolation,
} from './agentSensorTypes';

const STALE_MS = 24 * 60 * 60 * 1000;

export function isStale(sensor: AgentSensorSummary, now: number = Date.now()): boolean {
  if (sensor.status !== 'active') return false;
  if (!sensor.last_seen_at) return true;
  return now - Date.parse(sensor.last_seen_at) > STALE_MS;
}

export function statusTone(status: AgentSensorStatus): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'active') return 'success';
  if (status === 'revoked') return 'danger';
  if (status === 'disabled') return 'warning';
  return 'info';
}

const SENSITIVE_CLASSES = new Set([
  'sensitive',
  'credential',
  'deployment',
  'billing',
  'authentication',
  'customer_data',
  'decoy',
]);

export function pathClassTone(
  pathClass: string | null,
): 'info' | 'success' | 'warning' | 'danger' {
  if (!pathClass) return 'info';
  if (pathClass === 'decoy') return 'danger';
  if (SENSITIVE_CLASSES.has(pathClass)) return 'warning';
  if (pathClass === 'task_relevant') return 'success';
  return 'info';
}

export function severityTone(severity: string): 'info' | 'success' | 'warning' | 'danger' {
  if (severity === 'critical' || severity === 'high') return 'danger';
  if (severity === 'medium') return 'warning';
  return 'info';
}

export function isDecoyTouch(event: AgentTimelineEvent): boolean {
  return event.decoy_id !== null || event.path_class === 'decoy';
}

export function violationLabel(v: AgentViolation): string {
  return v.violation_type.replace(/_/g, ' ');
}

export function canManageSensors(scopes: readonly string[]): boolean {
  return scopes.includes('agent_sensors:manage');
}

export function canManagePolicies(scopes: readonly string[]): boolean {
  return scopes.includes('agent_policies:manage');
}
