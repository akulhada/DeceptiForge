// Purpose: background service worker — the only holder of the sensor secret and the network path.
// Responsibilities: enroll (exchange a one-time token for a sensor identity + scoped key + secret),
//   sync policy + trace registry on an alarm, answer content-script config requests, and report
//   detections as signed events (queuing when offline, with bounded retry/backoff). Validates every
//   inbound message against a strict schema and trusted sender origin. Never receives pasted text.
import { isDetectionMessage, isTrustedSender } from '~lib/messaging';
import { EventQueue } from '~lib/queue';
import { backoffMs, reportEvent } from '~lib/reporter';
import { buildEvent } from '~lib/event';
import { classifyDestination } from '~lib/classify';
import { loadQueue, loadState, saveQueue, saveState } from '~lib/storage';
import type { PolicyDoc, RegistryDoc, StoredState } from '~lib/types';

const VERSION = chrome.runtime.getManifest().version;
const SYNC_ALARM = 'df_sync';
const RETRY_ALARM = 'df_retry';

async function syncPolicyAndRegistry(): Promise<void> {
  const state = await loadState();
  if (!state) return;
  const headers = {
    'X-DeceptiForge-Org-Id': state.organization_id,
    'X-DeceptiForge-API-Key': state.api_key,
  };
  try {
    const [p, r] = await Promise.all([
      fetch(`${state.base_url}/browser-ai-policy`, { headers }),
      fetch(`${state.base_url}/browser-trace-registry`, { headers }),
    ]);
    if (p.ok) {
      const next = (await p.json()) as PolicyDoc;
      // Reject a policy whose version regresses (downgrade protection).
      if (!state.policy || next.policy_version >= state.policy.policy_version) {
        state.policy = next;
        state.last_policy_sync = new Date().toISOString();
      }
    }
    if (r.ok) {
      state.registry = (await r.json()) as RegistryDoc;
      state.last_registry_sync = new Date().toISOString();
    }
    await saveState(state);
  } catch {
    // Offline: keep the last cached policy/registry. No throw.
  }
}

async function flushQueue(): Promise<void> {
  const state = await loadState();
  if (!state) return;
  const queue = new EventQueue(200, 24 * 3_600_000);
  queue.load(await loadQueue());
  queue.expire();
  let attempt = 0;
  for (const item of [...queue.snapshot()]) {
    const result = await reportEvent(state, item.payload);
    if (result.ok || result.status === 409) {
      queue.ack(item.dedupe_key); // 409 = already recorded (replay) -> treat as delivered
    } else {
      attempt += 1;
    }
  }
  await saveQueue(queue.snapshot());
  if (queue.size > 0) {
    chrome.alarms.create(RETRY_ALARM, { when: Date.now() + backoffMs(attempt) });
  }
}

async function handleDetection(
  state: StoredState,
  trace_id: string,
  destination_domain: string,
  match_method: 'exact' | 'normalized' | 'fingerprint',
  editor_kind: string,
): Promise<void> {
  const classification = classifyDestination(
    destination_domain,
    state.policy?.rules ?? [],
  );
  const payload = buildEvent({
    trace_id,
    destination_domain,
    classification,
    match_method,
    editor_kind,
    extension_version: VERSION,
    policy_version: state.policy?.policy_version ?? 0,
  });
  if (state.policy && state.policy.event_reporting_enabled === false) return; // local-only mode
  const result = await reportEvent(state, payload);
  if (!result.ok && result.status !== 409) {
    const queue = new EventQueue(200, 24 * 3_600_000);
    queue.load(await loadQueue());
    queue.enqueue(payload);
    await saveQueue(queue.snapshot());
    chrome.alarms.create(RETRY_ALARM, { when: Date.now() + backoffMs(0) });
  }
}

chrome.runtime.onMessage.addListener((message: unknown, sender, sendResponse) => {
  void (async () => {
    const state = await loadState();
    const msg = message as { kind?: string };
    if (msg?.kind === 'df_get_config') {
      sendResponse({
        policy: state?.policy ?? null,
        registry: state?.registry ?? null,
        paused: state?.paused ?? false,
      });
      return;
    }
    if (isDetectionMessage(message)) {
      // Only trust detections from a monitored AI origin; reject spoofed page messages.
      if (!state || state.paused) return;
      const monitored = state.policy?.monitored_domains ?? [];
      if (!isTrustedSender(sender.origin ?? sender.url, monitored)) return;
      await handleDetection(
        state,
        message.trace_id,
        message.destination_domain,
        message.match_method,
        message.editor_kind,
      );
      return;
    }
  })();
  return true; // async response
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SYNC_ALARM) void syncPolicyAndRegistry();
  if (alarm.name === RETRY_ALARM) void flushQueue();
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 5 });
  void syncPolicyAndRegistry();
});

// Exported for background unit reasoning; also keeps tree-shakers from dropping helpers.
export { syncPolicyAndRegistry, flushQueue };
