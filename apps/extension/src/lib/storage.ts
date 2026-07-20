// Purpose: typed access to the extension's local storage.
// Responsibilities: read/write the single StoredState blob (sensor id, secret, scoped api key,
//   policy, compact registry, sync metadata, paused flag, bounded queue). Stores only minimized
//   data — never pasted text or conversation. Secret storage limitations are documented in
//   docs/BrowserPrivacy.md. Thin wrapper over chrome.storage.local.
import type { QueuedEvent } from './queue';
import type { StoredState } from './types';

const STATE_KEY = 'df_state';
const QUEUE_KEY = 'df_queue';

type ChromeLike = {
  storage?: { local?: { get(keys: string[]): Promise<Record<string, unknown>>; set(items: Record<string, unknown>): Promise<void>; remove(keys: string[]): Promise<void> } };
};

function area() {
  const c = (globalThis as unknown as { chrome?: ChromeLike }).chrome;
  if (!c?.storage?.local) throw new Error('chrome.storage.local unavailable');
  return c.storage.local;
}

export async function loadState(): Promise<StoredState | null> {
  const out = await area().get([STATE_KEY]);
  return (out[STATE_KEY] as StoredState | undefined) ?? null;
}

export async function saveState(state: StoredState): Promise<void> {
  await area().set({ [STATE_KEY]: state });
}

export async function clearState(): Promise<void> {
  await area().remove([STATE_KEY, QUEUE_KEY]);
}

export async function loadQueue(): Promise<QueuedEvent[]> {
  const out = await area().get([QUEUE_KEY]);
  return (out[QUEUE_KEY] as QueuedEvent[] | undefined) ?? [];
}

export async function saveQueue(items: readonly QueuedEvent[]): Promise<void> {
  await area().set({ [QUEUE_KEY]: items });
}
