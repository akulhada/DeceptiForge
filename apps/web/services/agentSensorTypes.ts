// Purpose: types for the AI agent activity sensor admin surface.
// Responsibilities: mirror the backend contracts (sensors, sessions, policies, timeline events,
//   violations). No behavior.

export type AgentSensorStatus = 'pending' | 'active' | 'disabled' | 'revoked';
export type AgentSessionStatus = 'active' | 'completed' | 'cancelled' | 'failed';

export interface AgentSensorSummary {
  id: string;
  sensor_public_id: string;
  name: string;
  adapter_type: string;
  version: string;
  status: AgentSensorStatus;
  last_seen_at: string | null;
  created_at: string;
}

export interface AgentSessionSummary {
  id: string;
  sensor_id: string;
  external_session_id: string;
  agent_type: string;
  status: AgentSessionStatus;
  task_summary_sanitized: string;
  scope_policy_id: string | null;
  correlation_id: string;
  started_at: string;
  ended_at: string | null;
}

export interface AgentPolicySummary {
  id: string;
  name: string;
  policy_version: number;
  allowed_paths: string[];
  denied_paths: string[];
  maximum_file_reads: number;
  maximum_sensitive_reads: number;
  allow_database_access: boolean;
  allow_network_access: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentPolicyBody {
  name: string;
  allowed_paths: string[];
  denied_paths: string[];
  allowed_tools: string[];
  denied_tools: string[];
  allowed_resource_types: string[];
  maximum_file_reads: number;
  maximum_sensitive_reads: number;
  allow_dependency_changes: boolean;
  allow_secret_file_access: boolean;
  allow_database_access: boolean;
  allow_network_access: boolean;
}

export interface AgentTimelineEvent {
  id: string;
  event_type: string;
  normalized_path: string | null;
  path_class: string | null;
  tool_name: string | null;
  resource_type: string | null;
  decoy_id: string | null;
  trace_id: string | null;
  result_status: string;
  minimized_metadata: string;
  observed_at: string;
}

export interface AgentViolation {
  id: string;
  event_id: string;
  violation_type: string;
  severity: string;
  confidence: number;
  policy_rule: string;
  explanation: string;
  created_at: string;
}

export interface EnrollmentToken {
  token: string;
  expires_at: string;
}
