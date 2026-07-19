// Purpose: authenticated client for RAG/MCP connectors and AI tripwire deployments.
// Responsibilities: send organization/API-key headers to organization-scoped routes, support the
//   POST lifecycle actions, list minimized events, and normalize errors into safe messages.
//   Credentials come from the in-session store and are never logged. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type {
  McpConnectorSummary,
  RagConnectorSummary,
  TripwireEvent,
  TripwirePreview,
  TripwireSummary,
} from './aiTripwireTypes';

export class AiTripwireApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'AiTripwireApiError';
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const session = getSession();
  if (!session) throw new AiTripwireApiError('not connected', 0);
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
    throw new AiTripwireApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new AiTripwireApiError('You are not authorized to perform this action.', response.status);
  }
  if (response.status === 409) {
    throw new AiTripwireApiError('This action is not allowed in the current state.', 409);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new AiTripwireApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

const dep = '/ai-tripwire-deployments';

export const aiTripwireApi = {
  ragConnectors: () => request<RagConnectorSummary[]>('/rag-connectors'),
  mcpConnectors: () => request<McpConnectorSummary[]>('/mcp-connectors'),
  deployments: () => request<TripwireSummary[]>(dep),
  deployment: (id: string) => request<TripwireSummary>(`${dep}/${id}`),
  preview: (id: string) => request<TripwirePreview>(`${dep}/${id}/preview`),
  events: (id: string) => request<TripwireEvent[]>(`${dep}/${id}/events`),
  submit: (id: string) => request<TripwireSummary>(`${dep}/${id}/submit`, 'POST'),
  approve: (id: string) => request<TripwireSummary>(`${dep}/${id}/approve`, 'POST'),
  reject: (id: string) => request<TripwireSummary>(`${dep}/${id}/reject`, 'POST'),
  deploy: (id: string) => request<TripwireSummary>(`${dep}/${id}/deploy`, 'POST'),
  retire: (id: string) => request<TripwireSummary>(`${dep}/${id}/retire`, 'POST'),
};
