// Purpose: bounded, minimized offline event queue.
// Responsibilities: hold only already-minimized event payloads when the backend is unavailable,
//   enforce a hard size bound (dropping oldest), expire stale entries, and dedupe by a stable
//   signature so a retry never double-reports. Never stores raw pasted text. No network here.
import type { EventPayload } from './types';

export interface QueuedEvent {
  payload: EventPayload;
  queued_at: number;
  dedupe_key: string;
}

export function dedupeKey(p: EventPayload): string {
  // Stable across retries; excludes any content. Same trace+destination+editor within a minute
  // collapses to one report.
  const minute = Math.floor(Date.parse(p.observed_at) / 60_000);
  return `${p.trace_id}|${p.destination_domain}|${p.event_type}|${minute}`;
}

export class EventQueue {
  private items: QueuedEvent[] = [];

  constructor(
    private readonly limit: number,
    private readonly maxAgeMs: number,
  ) {}

  get size(): number {
    return this.items.length;
  }

  snapshot(): readonly QueuedEvent[] {
    return this.items;
  }

  load(items: QueuedEvent[]): void {
    this.items = items.slice(-this.limit);
  }

  enqueue(payload: EventPayload, now: number = Date.now()): boolean {
    const key = dedupeKey(payload);
    if (this.items.some((q) => q.dedupe_key === key)) return false; // already queued -> no dup
    this.items.push({ payload, queued_at: now, dedupe_key: key });
    if (this.items.length > this.limit) this.items.shift(); // drop oldest, stay bounded
    return true;
  }

  expire(now: number = Date.now()): void {
    this.items = this.items.filter((q) => now - q.queued_at <= this.maxAgeMs);
  }

  // Remove a successfully sent item by its dedupe key.
  ack(key: string): void {
    this.items = this.items.filter((q) => q.dedupe_key !== key);
  }
}
