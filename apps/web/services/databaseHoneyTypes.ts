// Purpose: types for the database honey connector + deployment surface.
// Responsibilities: mirror the backend contracts. No behavior.

export type HoneyStatus =
  | 'draft'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'deploying'
  | 'deployed'
  | 'deployed_unmonitored'
  | 'verification_failed'
  | 'failed_activation'
  | 'failed'
  | 'cancelled'
  | 'drift_detected'
  | 'retiring'
  | 'retired'
  | 'rollback_pending'
  | 'rolled_back'
  | 'expired';

export interface ConnectorSummary {
  id: string;
  name: string;
  host_reference: string;
  database_name: string;
  ssl_mode: string;
  status: string;
  read_only_mode: boolean;
  last_tested_at: string | null;
  last_schema_sync_at: string | null;
  safe_error_code: string | null;
  created_at: string;
}

export interface HoneyDeploymentSummary {
  id: string;
  connector_id: string;
  target_schema: string;
  target_table: string;
  decoy_type: string;
  status: HoneyStatus;
  monitoring_activated: boolean;
  expires_at: string | null;
  failure_code: string | null;
  safe_failure_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface HoneyPreview {
  deployment_id: string;
  schema_name: string;
  table_name: string;
  decoy_type: string;
  columns: readonly string[];
  masked_values: Record<string, string>;
  trace_id: string;
  constraint_analysis: readonly string[];
  workflow_trigger_risk: readonly { code: string; detail: string }[];
  safety_ok: boolean;
  warnings: readonly string[];
  verification_plan: string;
  delete_predicate: string;
  expires_at: string | null;
}
