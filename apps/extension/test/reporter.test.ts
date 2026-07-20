// Purpose: verify signed reporting — correct headers/signature, body matches signed bytes, and the
//   pasted text never appears in the request. Backoff monotonic.
import { describe, expect, it, vi } from 'vitest';

import { backoffMs, reportEvent } from '../src/lib/reporter';
import { canonicalRequest, signRequest } from '../src/lib/signing';
import type { EventPayload, StoredState } from '../src/lib/types';

const state: StoredState = {
  sensor_public_id: 'dfs_test',
  signing_secret: 'secret-value',
  api_key: 'dfk_key',
  organization_id: 'org-1',
  base_url: 'https://api.example.com',
  paused: false,
};

const payload: EventPayload = {
  trace_id: 'DFAI-abc',
  destination_domain: 'chatgpt.com',
  event_type: 'shadow_ai_paste_detected',
  match_method: 'exact',
  confidence: 1,
  extension_version: '0.1.0',
  policy_version: 1,
  metadata: { editor: 'textarea' },
  observed_at: '2026-07-19T00:00:00.000Z',
};

describe('reportEvent', () => {
  it('sends a valid signed request with no raw content', async () => {
    let captured: { url: string; init: RequestInit } | null = null;
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      captured = { url, init };
      return new Response('{}', { status: 200 });
    }) as unknown as typeof fetch;

    const result = await reportEvent(state, payload, {
      fetchImpl,
      nonce: 'nonce123',
      timestamp: '1000',
    });
    expect(result.ok).toBe(true);
    const { url, init } = captured!;
    expect(url).toBe('https://api.example.com/monitoring/browser-events');
    const headers = init.headers as Record<string, string>;
    expect(headers['X-DeceptiForge-Sensor-Id']).toBe('dfs_test');
    // The signature matches the canonical request over the exact body bytes.
    const canonical = await canonicalRequest({
      method: 'POST',
      path: '/monitoring/browser-events',
      organizationId: 'org-1',
      sensorPublicId: 'dfs_test',
      timestamp: '1000',
      nonce: 'nonce123',
      body: init.body as string,
    });
    expect(headers['X-DeceptiForge-Signature']).toBe(await signRequest('secret-value', canonical));
    // Nothing resembling pasted text is present.
    expect(init.body as string).not.toContain('pasted');
  });
});

describe('backoffMs', () => {
  it('grows and caps', () => {
    expect(backoffMs(0)).toBeLessThan(backoffMs(1));
    expect(backoffMs(100)).toBeLessThanOrEqual(300_000);
  });
});
