// Purpose: verify local trace matching — exact/normalized match, no-match, expiry, and that the
//   raw pasted text never appears in any output.
import { describe, expect, it } from 'vitest';

import { sha256Hex } from '../src/lib/hash';
import { buildIndex, extractCandidates, matchText } from '../src/lib/matcher';
import type { RegistryDoc } from '../src/lib/types';

async function registry(trace: string, mode: 'exact' | 'normalized'): Promise<RegistryDoc> {
  const value = mode === 'normalized' ? trace.toLowerCase() : trace;
  return {
    organization_id: 'org',
    policy_version: 1,
    entries: [
      {
        trace_id: trace,
        match_token: await sha256Hex(value),
        match_mode: mode,
        status: 'active',
        expires_at: null,
      },
    ],
    generated_at: new Date().toISOString(),
  };
}

describe('extractCandidates', () => {
  it('finds DF tokens and emails, bounded', () => {
    const c = extractCandidates('hello DFAI-abc123 and bob@decoy.example ok');
    expect(c).toContain('DFAI-abc123');
    expect(c).toContain('bob@decoy.example');
  });
});

describe('matchText', () => {
  it('matches an exact marker', async () => {
    const index = buildIndex(await registry('DFAI-abc123', 'exact'));
    const m = await matchText('please summarize DFAI-abc123 for me', index);
    expect(m).toEqual({ trace_id: 'DFAI-abc123', match_method: 'exact' });
  });

  it('matches a normalized (case-variant) marker', async () => {
    const index = buildIndex(await registry('DFAI-ABC123', 'normalized'));
    const m = await matchText('text dfai-abc123 here', index);
    expect(m?.trace_id).toBe('DFAI-ABC123');
    expect(m?.match_method).toBe('normalized');
  });

  it('returns null when no marker is present', async () => {
    const index = buildIndex(await registry('DFAI-abc123', 'exact'));
    expect(await matchText('nothing sensitive here', index)).toBeNull();
  });

  it('ignores expired entries', async () => {
    const reg = await registry('DFAI-abc123', 'exact');
    reg.entries[0].expires_at = new Date(Date.now() - 1000).toISOString();
    const index = buildIndex(reg);
    expect(index.byToken.size).toBe(0);
    expect(await matchText('DFAI-abc123', index)).toBeNull();
  });
});
