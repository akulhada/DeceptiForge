// Purpose: shared types for the browser AI-paste sensor.
// Responsibilities: mirror the backend contracts (policy, registry, event) and define the strict
//   internal message schema. No behavior. Never carries pasted text or conversation content.

export type DestinationClass = 'approved' | 'conditional' | 'shadow' | 'unknown' | 'ignored';
export type TraceMatchMode = 'exact' | 'normalized';
export type MatchMethod = 'exact' | 'normalized' | 'fingerprint';

export type BrowserEventType =
  | 'ai_paste_trace_detected'
  | 'shadow_ai_paste_detected'
  | 'approved_ai_paste_detected'
  | 'repeated_ai_paste'
  | 'multi_tool_ai_exposure'
  | 'extension_policy_violation'
  | 'browser_sensor_disabled'
  | 'trace_registry_stale';

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
  trace_match_mode: TraceMatchMode;
  local_only_mode: boolean;
  event_reporting_enabled: boolean;
  show_user_notification: boolean;
  allow_pause: boolean;
  min_extension_version: string;
  policy_version: number;
  updated_at: string;
  signature?: string | null;
}

export interface RegistryEntry {
  trace_id: string;
  match_token: string;
  match_mode: TraceMatchMode;
  decoy_category?: string | null;
  status: string;
  expires_at?: string | null;
}

export interface RegistryDoc {
  organization_id: string;
  policy_version: number;
  entries: RegistryEntry[];
  generated_at: string;
}

// The minimized event payload sent to the backend. It never contains pasted text.
export interface EventPayload {
  trace_id: string;
  destination_domain: string;
  event_type: BrowserEventType;
  match_method: MatchMethod;
  confidence: number;
  extension_version: string;
  policy_version: number;
  excerpt_hash?: string | null;
  metadata: Record<string, string>;
  observed_at: string;
}

export interface StoredState {
  sensor_public_id: string;
  signing_secret: string;
  api_key: string;
  organization_id: string;
  base_url: string;
  policy?: PolicyDoc;
  registry?: RegistryDoc;
  paused: boolean;
  last_policy_sync?: string;
  last_registry_sync?: string;
}

// Strict content -> background message. `detail` is a matched trace id only; never raw text.
export interface DetectionMessage {
  kind: 'df_ai_paste_detection';
  version: 1;
  trace_id: string;
  destination_domain: string;
  match_method: MatchMethod;
  editor_kind: 'input' | 'textarea' | 'contenteditable';
}
