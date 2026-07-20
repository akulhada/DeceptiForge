// Purpose: authenticated client for the reliability / disaster-recovery admin surface.
// Responsibilities: read status/dependencies/backups/drills/failover-events and drive
//   restore-drill + failover request/approve. Normalizes errors into safe messages. Never receives
//   infrastructure credentials. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type {
  DependencyStatus,
  FailoverEvent,
  ReliabilityStatus,
  RestoreDrill,
} from './reliabilityTypes';

export class ReliabilityApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ReliabilityApiError';
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<T> {
  const session = getSession();
  if (!session) throw new ReliabilityApiError('not connected', 0);
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
      body: method === 'POST' ? JSON.stringify(body ?? {}) : undefined,
    });
  } catch {
    throw new ReliabilityApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new ReliabilityApiError('You are not authorized to perform this action.', response.status);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new ReliabilityApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const reliabilityApi = {
  status: () => request<ReliabilityStatus>('/admin/reliability/status'),
  dependencies: () => request<DependencyStatus>('/admin/reliability/dependencies'),
  drills: () => request<RestoreDrill[]>('/admin/reliability/restore-drills'),
  failoverEvents: () => request<FailoverEvent[]>('/admin/reliability/failover-events'),
  requestFailover: (reason: string) =>
    request<{ failover_state: string }>('/admin/reliability/failover/request', 'POST', { reason }),
  approveFailover: (reason: string) =>
    request<{ failover_state: string }>('/admin/reliability/failover/approve', 'POST', { reason }),
};
