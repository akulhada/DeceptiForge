// Purpose: types for the browser AI-paste sensor admin surface.
// Responsibilities: mirror the backend contracts (sensors, policy, events). No behavior.

export type SensorStatus = 'pending' | 'active' | 'revoked' | 'disabled';
export type DestinationClass = 'approved' | 'conditional' | 'shadow' | 'unknown' | 'ignored';

export interface SensorSummary {
  id: string;
  sensor_public_id: string;
  name: string;
  device_label: string | null;
  browser_family: string;
  extension_version: string;
  status: SensorStatus;
  last_seen_at: string | null;
  created_at: string;
}

export interface DomainRule {
  domain: string;
  classification: DestinationClass;
  label?: string | null;
}

export interface PolicyDoc {
  organization_id: string;
  enabled: boolean;
  monitored_domains: string[];
  rules: DomainRule[];
  trace_match_mode: 'exact' | 'normalized';
  local_only_mode: boolean;
  event_reporting_enabled: boolean;
  show_user_notification: boolean;
  allow_pause: boolean;
  min_extension_version: string;
  policy_version: number;
  updated_at: string;
  signature?: string | null;
}

export interface PolicyUpdate {
  enabled: boolean;
  trace_match_mode: 'exact' | 'normalized';
  local_only_mode: boolean;
  event_reporting_enabled: boolean;
  show_user_notification: boolean;
  allow_pause: boolean;
  min_extension_version: string;
  rules: DomainRule[];
}

export interface BrowserEvent {
  id: string;
  browser_sensor_id: string;
  trace_id: string;
  destination_domain: string;
  destination_classification: DestinationClass;
  event_type: string;
  match_method: string;
  confidence: number;
  extension_version: string;
  policy_version: number;
  minimized_metadata: string;
  correlation_id: string;
  observed_at: string;
}

export interface EnrollmentToken {
  token: string;
  expires_at: string;
}
