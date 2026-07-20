// Purpose: build the minimized event payload from a local match.
// Responsibilities: assemble only bounded, non-content fields — trace id, destination, event type,
//   match method, and small safe metadata (editor kind). Never includes pasted text. An optional
//   excerpt hash may be attached but never the excerpt itself.
import { eventTypeFor } from './classify';
import type { BrowserEventType, DestinationClass, EventPayload, MatchMethod } from './types';

export interface BuildEventInput {
  trace_id: string;
  destination_domain: string;
  classification: DestinationClass;
  match_method: MatchMethod;
  editor_kind: string;
  extension_version: string;
  policy_version: number;
  excerpt_hash?: string | null;
  observed_at?: string;
}

export function buildEvent(input: BuildEventInput): EventPayload {
  return {
    trace_id: input.trace_id,
    destination_domain: input.destination_domain,
    event_type: eventTypeFor(input.classification) as BrowserEventType,
    match_method: input.match_method,
    confidence: 1,
    extension_version: input.extension_version,
    policy_version: input.policy_version,
    excerpt_hash: input.excerpt_hash ?? null,
    // Only non-content, bounded metadata. The editor kind helps triage; it carries no text.
    metadata: { editor: input.editor_kind },
    observed_at: input.observed_at ?? new Date().toISOString(),
  };
}
