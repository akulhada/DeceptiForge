// Purpose: types for the AI (RAG/MCP) tripwire connector + deployment + event surface.
// Responsibilities: mirror the backend contracts. No behavior.

export type TripwireStatus =
  | 'draft'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'deploying'
  | 'deployed'
  | 'deployed_unmonitored'
  | 'verification_failed'
  | 'failed'
  | 'cancelled'
  | 'drift_detected'
  | 'retiring'
  | 'retired'
  | 'expired';

export type SurfaceType = 'rag_document' | 'mcp_resource' | 'mcp_config';

export interface RagConnectorSummary {
  id: string;
  name: string;
  connector_type: string;
  index_or_collection: string;
  namespace: string | null;
  status: string;
  last_tested_at: string | null;
  safe_error_code: string | null;
  created_at: string;
}

export interface McpConnectorSummary {
  id: string;
  name: string;
  server_reference: string;
  transport_type: string;
  status: string;
  last_tested_at: string | null;
  safe_error_code: string | null;
  created_at: string;
}

export interface TripwireSummary {
  id: string;
  surface_type: SurfaceType;
  connector_id: string;
  target_collection: string;
  decoy_kind: string;
  status: TripwireStatus;
  trace_id: string;
  external_asset_id: string | null;
  monitoring_activated: boolean;
  expires_at: string | null;
  safe_failure_code: string | null;
  safe_failure_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface TripwirePreview {
  deployment_id: string;
  surface_type: SurfaceType;
  connector_id: string;
  target_collection: string;
  decoy_kind: string;
  trace_token: string;
  trace_mechanisms: readonly string[];
  exact_content: string;
  metadata: Record<string, string>;
  safety_ok: boolean;
  verification_plan: string;
  retirement_plan: string;
  expires_at: string | null;
  expected_monitoring_registration: readonly string[];
  preview_hash: string;
}

export interface TripwireEvent {
  id: string;
  trace_id: string;
  surface_type: SurfaceType;
  event_type: string;
  source_id: string;
  monitor_identity: string;
  confidence: number;
  minimized_metadata: string;
  observed_at: string;
}
