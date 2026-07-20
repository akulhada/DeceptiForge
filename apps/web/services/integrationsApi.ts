// Purpose: authenticated client for SIEM/SOAR integrations, deliveries, and manual export.
// Responsibilities: send organization/API-key headers to organization-scoped routes, create/list/
//   test/disable integrations, read deliveries + dead letters, retry a delivery, and fetch a manual
//   incident export. Normalizes errors into safe messages. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type { CreateIntegration, DeadLetter, Delivery, IntegrationSummary } from './integrationsTypes';

export class IntegrationsApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'IntegrationsApiError';
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<T> {
  const session = getSession();
  if (!session) throw new IntegrationsApiError('not connected', 0);
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
    throw new IntegrationsApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new IntegrationsApiError('You are not authorized to perform this action.', response.status);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new IntegrationsApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

async function text(path: string): Promise<string> {
  const session = getSession();
  if (!session) throw new IntegrationsApiError('not connected', 0);
  const response = await fetch(`${session.baseUrl}${path}`, {
    cache: 'no-store',
    headers: {
      'X-DeceptiForge-Org-Id': session.organizationId,
      'X-DeceptiForge-API-Key': session.apiKey,
    },
  });
  if (!response.ok) throw new IntegrationsApiError(`Export failed (${response.status}).`, response.status);
  return response.text();
}

export const integrationsApi = {
  list: () => request<IntegrationSummary[]>('/security-integrations'),
  create: (body: CreateIntegration) =>
    request<IntegrationSummary>('/security-integrations', 'POST', body),
  test: (id: string) => request<{ ok: boolean; status: string }>(`/security-integrations/${id}/test`, 'POST'),
  disable: (id: string) =>
    request<IntegrationSummary>(`/security-integrations/${id}/disable`, 'POST'),
  deliveries: () => request<Delivery[]>('/integration-deliveries'),
  deadLetters: () => request<DeadLetter[]>('/integration-dead-letters'),
  retry: (id: string) => request<{ status: string }>(`/integration-deliveries/${id}/retry`, 'POST'),
  exportIncident: (incidentId: string, format: string) =>
    text(`/security-export/incidents/${incidentId}?format=${format}`),
};
