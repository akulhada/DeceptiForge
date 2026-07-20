// Purpose: send a minimized event to the backend as a signed, replay-safe request.
// Responsibilities: serialize the payload, generate a fresh nonce+timestamp, sign the canonical
//   request with the sensor secret, and POST it with the scoped api key. Injectable fetch/nonce so
//   it is testable. Never sends pasted text. Dependencies: signing, types.
import { canonicalRequest, signRequest } from './signing';
import type { EventPayload, StoredState } from './types';

const INGEST_PATH = '/monitoring/browser-events';

export interface ReportDeps {
  fetchImpl?: typeof fetch;
  nonce?: string;
  timestamp?: string;
}

export interface ReportResult {
  ok: boolean;
  status: number;
}

export async function reportEvent(
  state: StoredState,
  payload: EventPayload,
  deps: ReportDeps = {},
): Promise<ReportResult> {
  const fetchImpl = deps.fetchImpl ?? fetch;
  const nonce = deps.nonce ?? crypto.randomUUID().replace(/-/g, '');
  const timestamp = deps.timestamp ?? String(Date.now() / 1000);
  const body = JSON.stringify(payload);
  const canonical = await canonicalRequest({
    method: 'POST',
    path: INGEST_PATH,
    organizationId: state.organization_id,
    sensorPublicId: state.sensor_public_id,
    timestamp,
    nonce,
    body,
  });
  const signature = await signRequest(state.signing_secret, canonical);
  const res = await fetchImpl(`${state.base_url}${INGEST_PATH}`, {
    method: 'POST',
    // Exact bytes must match the signed body; do not re-serialize elsewhere.
    body,
    headers: {
      'content-type': 'application/json',
      'X-DeceptiForge-Org-Id': state.organization_id,
      'X-DeceptiForge-API-Key': state.api_key,
      'X-DeceptiForge-Sensor-Id': state.sensor_public_id,
      'X-DeceptiForge-Nonce': nonce,
      'X-DeceptiForge-Timestamp': timestamp,
      'X-DeceptiForge-Signature': signature,
    },
  });
  return { ok: res.ok, status: res.status };
}

// Exponential backoff with a cap, for the background retry loop.
export function backoffMs(attempt: number, baseMs = 1_000, capMs = 300_000): number {
  return Math.min(capMs, baseMs * 2 ** Math.max(0, attempt));
}
