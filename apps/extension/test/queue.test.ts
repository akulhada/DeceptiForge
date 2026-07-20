// Purpose: verify the offline queue — bounds, expiry, dedupe, and that only minimized payloads are
//   stored (no pasted text).
import { describe, expect, it } from 'vitest';

import { EventQueue } from '../src/lib/queue';
import type { EventPayload } from '../src/lib/types';

function payload(trace: string, at: string): EventPayload {
  return {
    trace_id: trace,
    destination_domain: 'chatgpt.com',
    event_type: 'shadow_ai_paste_detected',
    match_method: 'exact',
    confidence: 1,
    extension_version: '0.1.0',
    policy_version: 1,
    metadata: { editor: 'textarea' },
    observed_at: at,
  };
}

describe('EventQueue', () => {
  it('stores only minimized payload (no text field)', () => {
    const q = new EventQueue(10, 1_000_000);
    q.enqueue(payload('DFAI-1', new Date().toISOString()));
    const item = q.snapshot()[0];
    expect(JSON.stringify(item)).not.toContain('pasted');
    expect(Object.keys(item.payload.metadata)).toEqual(['editor']);
  });

  it('enforces the size bound by dropping oldest', () => {
    const q = new EventQueue(2, 1_000_000);
    for (let i = 0; i < 5; i++) {
      q.enqueue(payload(`DFAI-${i}`, new Date(Date.now() + i * 60_000).toISOString()));
    }
    expect(q.size).toBe(2);
  });

  it('dedupes identical events within the same minute', () => {
    const q = new EventQueue(10, 1_000_000);
    const at = new Date().toISOString();
    expect(q.enqueue(payload('DFAI-1', at))).toBe(true);
    expect(q.enqueue(payload('DFAI-1', at))).toBe(false);
    expect(q.size).toBe(1);
  });

  it('expires stale entries', () => {
    const q = new EventQueue(10, 1_000);
    q.enqueue(payload('DFAI-1', new Date().toISOString()), Date.now() - 5_000);
    q.expire(Date.now());
    expect(q.size).toBe(0);
  });
});
