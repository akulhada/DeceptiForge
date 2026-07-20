// Purpose: local, privacy-preserving trace matching.
// Responsibilities: extract candidate marker substrings from pasted text, hash them locally, and
//   compare against the registry's irreversible match tokens. The raw pasted text and the raw
//   marker never leave the page — only a matched trace id (and optional excerpt hash) is reported.
//   Bounded work: candidates are capped and the registry lookup is O(1). No DOM, no network.
import { sha256Hex } from './hash';
import type { MatchMethod, RegistryDoc, RegistryEntry, TraceMatchMode } from './types';

// DeceptiForge trace tokens (e.g. DFAI-abc123, DFH-.., DFG-DB-..) plus decoy email references.
const TOKEN_RE = /\bDF[A-Z]{1,4}-[A-Za-z0-9-]{4,40}\b/gi;
const EMAIL_RE = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g;
const MAX_CANDIDATES = 64;
const MAX_SCAN_CHARS = 20_000; // bound work; never scan unbounded page text

export function extractCandidates(text: string): string[] {
  const scan = text.length > MAX_SCAN_CHARS ? text.slice(0, MAX_SCAN_CHARS) : text;
  const found = new Set<string>();
  for (const re of [TOKEN_RE, EMAIL_RE]) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(scan)) !== null) {
      found.add(m[0]);
      if (found.size >= MAX_CANDIDATES) return [...found];
    }
  }
  return [...found];
}

export interface TraceIndex {
  byToken: Map<string, RegistryEntry>;
  mode: TraceMatchMode;
}

export function buildIndex(registry: RegistryDoc): TraceIndex {
  const now = Date.now();
  const byToken = new Map<string, RegistryEntry>();
  let mode: TraceMatchMode = 'exact';
  for (const entry of registry.entries) {
    if (entry.status !== 'active') continue;
    if (entry.expires_at && Date.parse(entry.expires_at) < now) continue; // expired -> ignored
    byToken.set(entry.match_token, entry);
    mode = entry.match_mode;
  }
  return { byToken, mode };
}

export interface Match {
  trace_id: string;
  match_method: MatchMethod;
}

// Return the first candidate that maps to a live registry entry, or null. Hashing is the only work
// per candidate; the raw candidate is discarded immediately.
export async function matchText(text: string, index: TraceIndex): Promise<Match | null> {
  if (index.byToken.size === 0) return null;
  for (const candidate of extractCandidates(text)) {
    const exact = await sha256Hex(candidate.trim());
    const hitExact = index.byToken.get(exact);
    if (hitExact) return { trace_id: hitExact.trace_id, match_method: hitExact.match_mode };
    if (index.mode === 'normalized') {
      const norm = await sha256Hex(candidate.trim().toLowerCase());
      const hitNorm = index.byToken.get(norm);
      if (hitNorm) return { trace_id: hitNorm.trace_id, match_method: hitNorm.match_mode };
    }
  }
  return null;
}
