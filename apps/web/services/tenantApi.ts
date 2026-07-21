// Purpose: authenticated tenant API client for the production-like dashboard.
// Responsibilities: send organization/API-key headers to organization-scoped endpoints, never the
//   demo routes, and normalize errors. Credentials come from the in-session store, not env vars.
// Dependencies: the tenant session and shared demo types (reused for rendering).
'use client';

import { getSession } from './authSession';
import type { Alert, Incident, IncidentNarrative, RepositoryProfile } from './types';

export class TenantApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'TenantApiError';
  }
}

export interface WhoAmI {
  organization_id: string;
  role: string;
  scopes: readonly string[];
}

export interface TenantRepository {
  repository_id: string;
  name: string;
  profile: RepositoryProfile;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const session = getSession();
  if (!session) throw new TenantApiError('not connected', 0);
  let response: Response;
  try {
    response = await fetch(`${session.baseUrl}${path}`, {
      ...init,
      cache: 'no-store',
      headers: {
        'content-type': 'application/json',
        'X-DeceptiForge-Org-Id': session.organizationId,
        'X-DeceptiForge-API-Key': session.apiKey,
        ...init?.headers,
      },
    });
  } catch {
    throw new TenantApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new TenantApiError('Invalid or unauthorized credentials.', response.status);
  }
  if (!response.ok) {
    throw new TenantApiError(`Request to ${path} failed (${response.status}).`, response.status);
  }
  return (await response.json()) as T;
}

export const tenantApi = {
  whoami: () => request<WhoAmI>('/whoami'),
  repositories: () =>
    request<{ repositories: readonly TenantRepository[] }>('/repositories').then(
      (r) => r.repositories,
    ),
  alerts: () => request<{ alerts: readonly Alert[] }>('/alerts').then((r) => r.alerts),
  incidents: () =>
    request<{ incidents: readonly Incident[] }>('/incidents').then((r) => r.incidents),
  generateIncidentNarrative: (incidentId: string) =>
    request<IncidentNarrative>(`/incidents/${incidentId}/narrative`, { method: 'POST' }),
};
