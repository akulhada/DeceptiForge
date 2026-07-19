// Purpose: authenticated client for the decoy deployment lifecycle endpoints.
// Responsibilities: send organization/API-key headers to organization-scoped deployment routes,
//   support the POST lifecycle actions, and normalize errors into safe messages. Credentials come
//   from the in-session store, never env vars, and are never logged. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type {
  DeploymentAuditEntry,
  DeploymentPreview,
  DeploymentSummary,
} from './deploymentTypes';

export class DeploymentApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'DeploymentApiError';
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const session = getSession();
  if (!session) throw new DeploymentApiError('not connected', 0);
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
    throw new DeploymentApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new DeploymentApiError('You are not authorized to perform this action.', response.status);
  }
  if (response.status === 409) {
    throw new DeploymentApiError('This action is not allowed in the current state.', 409);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new DeploymentApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

const base = '/decoy-deployments';

export const deploymentsApi = {
  list: () => request<DeploymentSummary[]>(base),
  get: (id: string) => request<DeploymentSummary>(`${base}/${id}`),
  preview: (id: string) => request<DeploymentPreview>(`${base}/${id}/preview`),
  audit: (id: string) => request<DeploymentAuditEntry[]>(`${base}/${id}/audit`),
  submit: (id: string) => request<DeploymentSummary>(`${base}/${id}/submit`, 'POST'),
  approve: (id: string) => request<DeploymentSummary>(`${base}/${id}/approve`, 'POST'),
  reject: (id: string) => request<DeploymentSummary>(`${base}/${id}/reject`, 'POST'),
  deploy: (id: string) => request<DeploymentSummary>(`${base}/${id}/deploy`, 'POST'),
  retire: (id: string) => request<DeploymentSummary>(`${base}/${id}/retire`, 'POST'),
  rollback: (id: string) => request<DeploymentSummary>(`${base}/${id}/rollback`, 'POST'),
};
