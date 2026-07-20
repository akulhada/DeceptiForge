// Purpose: authenticated client for browser sensors, policy, and paste events.
// Responsibilities: send organization/API-key headers to organization-scoped routes, support
//   enrollment-token creation, sensor revoke/rotate, policy read/update, and event listing, and
//   normalize errors into safe messages. Credentials come from the in-session store and are never
//   logged. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type {
  BrowserEvent,
  EnrollmentToken,
  PolicyDoc,
  PolicyUpdate,
  SensorSummary,
} from './browserSensorTypes';

export class BrowserSensorApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'BrowserSensorApiError';
  }
}

async function request<T>(
  path: string,
  method: 'GET' | 'POST' | 'PUT' = 'GET',
  body?: unknown,
): Promise<T> {
  const session = getSession();
  if (!session) throw new BrowserSensorApiError('not connected', 0);
  let response: Response;
  try {
    response = await fetch(`${session.baseUrl}${path}`, {
      method,
      cache: 'no-store',
      headers: {
        'content-type': 'application/json',
        'X-DeceptiForge-Org-Id': session.organizationId,
        'X-DeceptiForge-API-Key': session.apiKey,
      },
      body: method === 'GET' ? undefined : JSON.stringify(body ?? {}),
    });
  } catch {
    throw new BrowserSensorApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new BrowserSensorApiError('You are not authorized to perform this action.', response.status);
  }
  if (response.status === 409) {
    throw new BrowserSensorApiError('This action is not allowed in the current state.', 409);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new BrowserSensorApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const browserSensorApi = {
  sensors: () => request<SensorSummary[]>('/browser-sensors'),
  createEnrollmentToken: () =>
    request<EnrollmentToken>('/browser-sensors/enrollment-tokens', 'POST'),
  revoke: (id: string) => request<SensorSummary>(`/browser-sensors/${id}/revoke`, 'POST'),
  rotate: (id: string) => request<{ signing_secret: string }>(`/browser-sensors/${id}/rotate`, 'POST'),
  policy: () => request<PolicyDoc>('/browser-ai-policy'),
  updatePolicy: (update: PolicyUpdate) => request<PolicyDoc>('/browser-ai-policy', 'PUT', update),
  events: () => request<BrowserEvent[]>('/browser-events'),
};
