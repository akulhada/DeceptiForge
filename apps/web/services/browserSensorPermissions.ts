// Purpose: pure helpers for the browser-sensor admin view — status tone, staleness, action gating,
//   and exposure labels. No network or DOM.
// Responsibilities: decide which sensor actions a viewer may take from status + scopes, flag stale
//   sensors, and map an event type to an AI-native exposure label for display. Dependencies: types.
import type { BrowserEvent, DestinationClass, SensorStatus, SensorSummary } from './browserSensorTypes';

export type SensorAction = 'revoke' | 'rotate';

const REQUIRED_SCOPE: Record<SensorAction, string> = {
  revoke: 'browser_sensors:manage',
  rotate: 'browser_sensors:manage',
};

export function availableActions(
  status: SensorStatus,
  scopes: readonly string[],
): readonly SensorAction[] {
  if (status === 'revoked') return [];
  const has = new Set(scopes);
  return (['rotate', 'revoke'] as SensorAction[]).filter((a) => has.has(REQUIRED_SCOPE[a]));
}

const STALE_MS = 24 * 60 * 60 * 1000;

export function isStale(sensor: SensorSummary, now: number = Date.now()): boolean {
  if (sensor.status !== 'active') return false;
  if (!sensor.last_seen_at) return true;
  return now - Date.parse(sensor.last_seen_at) > STALE_MS;
}

export function statusTone(status: SensorStatus): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'active') return 'success';
  if (status === 'revoked') return 'danger';
  if (status === 'disabled') return 'warning';
  return 'info';
}

export function classificationTone(
  c: DestinationClass,
): 'info' | 'success' | 'warning' | 'danger' {
  if (c === 'approved') return 'success';
  if (c === 'shadow' || c === 'unknown') return 'danger';
  if (c === 'conditional') return 'warning';
  return 'info';
}

const EXPOSURE_LABEL: Record<string, string> = {
  approved_ai_paste_detected: 'Approved AI paste',
  shadow_ai_paste_detected: 'Shadow AI exposure',
  ai_paste_trace_detected: 'AI paste leak',
  repeated_ai_paste: 'Repeated AI paste',
  multi_tool_ai_exposure: 'Multi-tool AI exposure',
};

export function exposureLabel(event: BrowserEvent): string {
  return EXPOSURE_LABEL[event.event_type] ?? 'AI paste exposure';
}
