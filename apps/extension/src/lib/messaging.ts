// Purpose: strict validation of content -> background messages and sender origin.
// Responsibilities: reject any message that does not exactly match the detection schema, and reject
//   senders whose origin is not a monitored AI domain. This blocks malicious pages from spoofing
//   extension messages or injecting arbitrary fields. No DOM, no network.
import { normalizeDomain } from './classify';
import type { DetectionMessage, MatchMethod } from './types';

const MATCH_METHODS: ReadonlySet<MatchMethod> = new Set(['exact', 'normalized', 'fingerprint']);
const EDITOR_KINDS = new Set(['input', 'textarea', 'contenteditable']);

export function isDetectionMessage(value: unknown): value is DetectionMessage {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.kind === 'df_ai_paste_detection' &&
    v.version === 1 &&
    typeof v.trace_id === 'string' &&
    v.trace_id.length > 0 &&
    v.trace_id.length <= 128 &&
    typeof v.destination_domain === 'string' &&
    v.destination_domain.length > 0 &&
    v.destination_domain.length <= 253 &&
    typeof v.match_method === 'string' &&
    MATCH_METHODS.has(v.match_method as MatchMethod) &&
    typeof v.editor_kind === 'string' &&
    EDITOR_KINDS.has(v.editor_kind)
  );
}

// Accept a message only from a sender whose origin host is a monitored AI domain.
export function isTrustedSender(senderOrigin: string | undefined, monitored: string[]): boolean {
  if (!senderOrigin) return false;
  let host: string;
  try {
    host = new URL(senderOrigin).hostname;
  } catch {
    return false;
  }
  const h = normalizeDomain(host);
  return monitored.some((d) => {
    const rd = normalizeDomain(d);
    return h === rd || h.endsWith('.' + rd);
  });
}
