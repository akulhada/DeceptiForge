// Purpose: verify AI tripwire action gating, drift detection, monitoring/exposure labels.
import { describe, expect, it } from 'vitest';

import {
  availableActions,
  exposureLabel,
  isDrift,
  isTerminal,
  monitoringLabel,
  surfaceLabel,
} from './aiTripwirePermissions';
import type { TripwireEvent, TripwireSummary } from './aiTripwireTypes';

const ALL = [
  'ai_tripwires:read',
  'ai_tripwires:create',
  'ai_tripwires:approve',
  'ai_tripwires:deploy',
  'ai_tripwires:retire',
];

describe('availableActions', () => {
  it('gates submit/approve/deploy by status and scope', () => {
    expect(availableActions('draft', ['ai_tripwires:create'])).toEqual(['submit']);
    expect(availableActions('draft', ['ai_tripwires:read'])).toEqual([]);
    expect(availableActions('awaiting_approval', ['ai_tripwires:approve'])).toEqual([
      'approve',
      'reject',
    ]);
    expect(availableActions('approved', ['ai_tripwires:deploy'])).toEqual(['deploy']);
  });

  it('offers retire on deployed, drift, verification_failed, and expired', () => {
    expect(availableActions('deployed', ALL)).toEqual(['retire']);
    expect(availableActions('drift_detected', ALL)).toEqual(['retire']);
    expect(availableActions('verification_failed', ALL)).toEqual(['retire']);
    expect(availableActions('expired', ALL)).toEqual(['retire']);
  });

  it('offers no actions on terminal states', () => {
    for (const status of ['retired', 'rejected', 'cancelled'] as const) {
      expect(availableActions(status, ALL)).toEqual([]);
      expect(isTerminal(status)).toBe(true);
    }
  });
});

describe('isDrift', () => {
  it('flags drift_detected only', () => {
    expect(isDrift('drift_detected')).toBe(true);
    expect(isDrift('deployed')).toBe(false);
  });
});

describe('monitoringLabel', () => {
  const base: TripwireSummary = {
    id: 'd',
    surface_type: 'rag_document',
    connector_id: 'c',
    target_collection: 'deceptiforge_decoys',
    decoy_kind: 'architecture_note',
    status: 'deployed',
    trace_id: 'DFAI-abc',
    external_asset_id: 'rag:x',
    monitoring_activated: true,
    expires_at: null,
    safe_failure_code: null,
    safe_failure_message: null,
    created_at: '',
    updated_at: '',
  };

  it('labels active vs verification-failed vs not activated', () => {
    expect(monitoringLabel(base)).toBe('Active');
    expect(monitoringLabel({ ...base, monitoring_activated: false })).toBe('Not activated');
    expect(
      monitoringLabel({ ...base, monitoring_activated: false, status: 'verification_failed' }),
    ).toBe('Not activated (verification failed)');
  });
});

describe('surfaceLabel', () => {
  it('names each surface', () => {
    expect(surfaceLabel('rag_document')).toBe('RAG document');
    expect(surfaceLabel('mcp_resource')).toBe('MCP resource');
    expect(surfaceLabel('mcp_config')).toBe('MCP config');
  });
});

describe('exposureLabel', () => {
  const base: TripwireEvent = {
    id: 'e',
    trace_id: 'DFAI-abc',
    surface_type: 'rag_document',
    event_type: 'document_retrieved',
    source_id: 'agent',
    monitor_identity: 'monitor',
    confidence: 1,
    minimized_metadata: '{}',
    observed_at: '2026-07-19T00:00:00',
  };

  it('maps event types to AI-native exposure labels deterministically', () => {
    expect(exposureLabel(base)).toBe('RAG retrieval exposure');
    expect(exposureLabel({ ...base, event_type: 'trace_in_answer' })).toBe('RAG answer leak');
    expect(exposureLabel({ ...base, event_type: 'resource_read' })).toBe('MCP resource access');
    expect(exposureLabel({ ...base, event_type: 'config_loaded' })).toBe('MCP config exposure');
    expect(exposureLabel({ ...base, event_type: 'agent_touched' })).toBe('AI agent decoy touch');
    expect(exposureLabel({ ...base, event_type: 'unknown_future' })).toBe('AI-native exposure');
  });
});
