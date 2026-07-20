// Purpose: authenticated client for the coverage engine.
// Responsibilities: send organization/API-key headers to organization-scoped routes, read the
//   current status/snapshots/surfaces/gaps/recommendations/methodology, trigger a recalculation,
//   and accept/dismiss a recommendation. Normalizes errors into safe messages. Dependencies:
//   session, types.
'use client';

import { getSession } from './authSession';
import type {
  CoverageGap,
  CoverageMethodology,
  CoverageRecommendation,
  CoverageSnapshot,
  CoverageStatus,
  CoverageSurface,
} from './coverageTypes';

export class CoverageApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'CoverageApiError';
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const session = getSession();
  if (!session) throw new CoverageApiError('not connected', 0);
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
      body: method === 'POST' ? '{}' : undefined,
    });
  } catch {
    throw new CoverageApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new CoverageApiError('You are not authorized to perform this action.', response.status);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new CoverageApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const coverageApi = {
  status: () => request<CoverageStatus>('/coverage'),
  snapshots: () => request<CoverageSnapshot[]>('/coverage/snapshots'),
  surfaces: () => request<CoverageSurface[]>('/coverage/surfaces'),
  gaps: () => request<CoverageGap[]>('/coverage/gaps'),
  recommendations: () => request<CoverageRecommendation[]>('/coverage/recommendations'),
  methodology: () => request<CoverageMethodology>('/coverage/methodology'),
  recalculate: () => request<CoverageSnapshot>('/coverage/recalculate', 'POST'),
  acceptRecommendation: (id: string) =>
    request<{ status: string; auto_deployed: boolean }>(
      `/coverage/recommendations/${id}/accept`, 'POST',
    ),
  dismissRecommendation: (id: string) =>
    request<{ status: string }>(`/coverage/recommendations/${id}/dismiss`, 'POST'),
};
