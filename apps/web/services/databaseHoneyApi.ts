// Purpose: authenticated client for database connectors and honey deployments.
// Responsibilities: send organization/API-key headers to organization-scoped routes, support the
//   POST lifecycle actions, and normalize errors into safe messages. Credentials come from the
//   in-session store and are never logged. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type {
  ConnectorSummary,
  HoneyDeploymentSummary,
  HoneyPreview,
} from './databaseHoneyTypes';

export class DatabaseHoneyApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'DatabaseHoneyApiError';
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const session = getSession();
  if (!session) throw new DatabaseHoneyApiError('not connected', 0);
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
    throw new DatabaseHoneyApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new DatabaseHoneyApiError('You are not authorized to perform this action.', response.status);
  }
  if (response.status === 409) {
    throw new DatabaseHoneyApiError('This action is not allowed in the current state.', 409);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new DatabaseHoneyApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

const dep = '/database-honey-deployments';

export const databaseHoneyApi = {
  connectors: () => request<ConnectorSummary[]>('/database-connectors'),
  deployments: () => request<HoneyDeploymentSummary[]>(dep),
  deployment: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}`),
  preview: (id: string) => request<HoneyPreview>(`${dep}/${id}/preview`),
  submit: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}/submit`, 'POST'),
  approve: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}/approve`, 'POST'),
  reject: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}/reject`, 'POST'),
  deploy: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}/deploy`, 'POST'),
  retire: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}/retire`, 'POST'),
  rollback: (id: string) => request<HoneyDeploymentSummary>(`${dep}/${id}/rollback`, 'POST'),
};
