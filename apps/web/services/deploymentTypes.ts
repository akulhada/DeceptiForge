// Purpose: types for the decoy deployment lifecycle surface used by the dashboard.
// Responsibilities: mirror the backend deployment summary/preview/audit contracts. No behavior.

export type DeploymentStatus =
  | 'draft'
  | 'awaiting_approval'
  | 'preview_stale'
  | 'reapproval_required'
  | 'approved'
  | 'rejected'
  | 'deploying'
  | 'deployed'
  | 'deployed_unmonitored'
  | 'verification_failed'
  | 'failed_activation'
  | 'failed'
  | 'cancelled'
  | 'retiring'
  | 'retired'
  | 'rollback_pending'
  | 'rolled_back'
  | 'expired';

export interface DeploymentSummary {
  id: string;
  repository_id: string;
  decoy_plan_id: string;
  status: DeploymentStatus;
  target_branch: string;
  base_commit_sha: string;
  pull_request_number: number | null;
  pull_request_url: string | null;
  monitoring_activated: boolean;
  expires_at: string | null;
  failure_code: string | null;
  safe_failure_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChangeSetItem {
  decoy_id: string;
  decoy_type: string;
  target_path: string;
  operation: 'create' | 'append' | 'modify';
  trace_identifier: string;
  proposed_content_hash: string;
  unified_diff: string;
  warnings: readonly string[];
}

export interface DeploymentPreview {
  deployment_id: string;
  repository_id: string;
  target_branch: string;
  base_branch: string;
  base_commit_sha: string;
  items: readonly ChangeSetItem[];
  decoy_types: readonly string[];
  trace_identifiers: readonly string[];
  validation_decision: string;
  collision_ok: boolean;
  expires_at: string | null;
  rollback_strategy: string;
  warnings: readonly string[];
  changed_files: number;
  changed_bytes: number;
  blast_radius: string;
  preview_hash: string;
}

export interface DeploymentAuditEntry {
  event_type: string;
  request_id: string;
  safe_metadata: string;
  created_at: string;
}
