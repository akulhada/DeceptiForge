// Purpose: decide which AI tripwire actions a viewer may take, given status and scopes, and label
//   AI-native exposure/monitoring state.
// Responsibilities: pure mapping used by the dashboard to show only permitted actions, warn on
//   drift, and classify events into an AI-native exposure label for display. No network or DOM.
// Dependencies: tripwire types.
import type { SurfaceType, TripwireEvent, TripwireStatus, TripwireSummary } from './aiTripwireTypes';

export type TripwireAction = 'submit' | 'approve' | 'reject' | 'deploy' | 'retire';

const REQUIRED_SCOPE: Record<TripwireAction, string> = {
  submit: 'ai_tripwires:create',
  approve: 'ai_tripwires:approve',
  reject: 'ai_tripwires:approve',
  deploy: 'ai_tripwires:deploy',
  retire: 'ai_tripwires:retire',
};

const ACTIONS_FOR_STATUS: Partial<Record<TripwireStatus, readonly TripwireAction[]>> = {
  draft: ['submit'],
  awaiting_approval: ['approve', 'reject'],
  approved: ['deploy'],
  failed: ['submit'],
  deployed: ['retire'],
  deployed_unmonitored: ['retire'],
  verification_failed: ['retire'],
  drift_detected: ['retire'],
  expired: ['retire'],
};

export function availableActions(
  status: TripwireStatus,
  scopes: readonly string[],
): readonly TripwireAction[] {
  const scopeSet = new Set(scopes);
  return (ACTIONS_FOR_STATUS[status] ?? []).filter((action) => scopeSet.has(REQUIRED_SCOPE[action]));
}

export function isDrift(status: TripwireStatus): boolean {
  return status === 'drift_detected';
}

export function isTerminal(status: TripwireStatus): boolean {
  return status === 'rejected' || status === 'cancelled' || status === 'retired';
}

export function monitoringLabel(summary: TripwireSummary): string {
  if (summary.monitoring_activated) return 'Active';
  if (summary.status === 'verification_failed' || summary.status === 'deployed_unmonitored') {
    return 'Not activated (verification failed)';
  }
  return 'Not activated';
}

export function surfaceLabel(surface: SurfaceType): string {
  if (surface === 'rag_document') return 'RAG document';
  if (surface === 'mcp_config') return 'MCP config';
  return 'MCP resource';
}

// Deterministic, presentation-only mapping of an event type to an AI-native exposure label. This
// mirrors the backend classification for display; the backend remains the source of truth.
const EXPOSURE_LABEL: Record<string, string> = {
  document_retrieved: 'RAG retrieval exposure',
  chunk_retrieved: 'RAG retrieval exposure',
  trace_in_model_input: 'RAG retrieval exposure',
  trace_in_answer: 'RAG answer leak',
  document_exported: 'RAG retrieval exposure',
  document_copied: 'RAG retrieval exposure',
  resource_listed: 'MCP resource access',
  resource_read: 'MCP resource access',
  resource_referenced: 'MCP resource access',
  uri_requested: 'MCP resource access',
  metadata_copied: 'MCP resource access',
  config_loaded: 'MCP config exposure',
  agent_touched: 'AI agent decoy touch',
};

export function exposureLabel(event: TripwireEvent): string {
  return EXPOSURE_LABEL[event.event_type] ?? 'AI-native exposure';
}
