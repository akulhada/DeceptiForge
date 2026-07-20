// Purpose: types for the SIEM/SOAR integrations admin surface.
// Responsibilities: mirror the backend contracts (integrations, deliveries, dead letters). No
//   behavior.

export type IntegrationType =
  | 'generic_webhook'
  | 'splunk_hec'
  | 'microsoft_sentinel'
  | 'elastic'
  | 'datadog';

export type IntegrationStatus = 'pending' | 'active' | 'degraded' | 'disabled' | 'revoked';

export interface IntegrationSummary {
  id: string;
  integration_type: IntegrationType;
  name: string;
  status: IntegrationStatus;
  endpoint_reference: string;
  payload_profile: string;
  minimum_severity: string;
  include_narrative: boolean;
  last_tested_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  safe_failure_code: string | null;
  created_at: string;
}

export interface CreateIntegration {
  integration_type: IntegrationType;
  name: string;
  endpoint: string;
  secret?: string;
  options?: Record<string, string>;
  event_types?: string[];
  surface_types?: string[];
  minimum_severity: string;
  payload_profile: string;
  include_narrative: boolean;
  include_coverage_events: boolean;
  include_operational_events: boolean;
}

export interface Delivery {
  id: string;
  integration_id: string;
  source_type: string;
  source_id: string;
  event_type: string;
  status: string;
  attempt_count: number;
  response_status: number | null;
  safe_error_code: string | null;
  created_at: string;
  delivered_at: string | null;
}

export interface DeadLetter {
  id: string;
  integration_id: string;
  delivery_id: string;
  reason_code: string;
  attempt_count: number;
  payload_hash: string;
  final_failed_at: string;
}
