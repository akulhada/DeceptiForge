// Purpose: authenticated client for agent sensors, sessions, policies, timeline, and violations.
// Responsibilities: send organization/API-key headers to organization-scoped routes, support
//   enrollment-token creation, sensor revoke, policy CRUD, and session timeline/violation reads,
//   normalizing errors into safe messages. Dependencies: session, types.
'use client';

import { getSession } from './authSession';
import type {
  AgentPolicyBody,
  AgentPolicySummary,
  AgentSensorSummary,
  AgentSessionSummary,
  AgentTimelineEvent,
  AgentViolation,
  EnrollmentToken,
} from './agentSensorTypes';

export class AgentSensorApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'AgentSensorApiError';
  }
}

async function request<T>(
  path: string,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
  body?: unknown,
): Promise<T> {
  const session = getSession();
  if (!session) throw new AgentSensorApiError('not connected', 0);
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
      body: method === 'GET' || method === 'DELETE' ? undefined : JSON.stringify(body ?? {}),
    });
  } catch {
    throw new AgentSensorApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (response.status === 401 || response.status === 403) {
    throw new AgentSensorApiError('You are not authorized to perform this action.', response.status);
  }
  if (response.status === 409) {
    throw new AgentSensorApiError('This action is not allowed in the current state.', 409);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new AgentSensorApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const agentSensorApi = {
  sensors: () => request<AgentSensorSummary[]>('/agent-sensors'),
  createEnrollmentToken: () =>
    request<EnrollmentToken>('/agent-sensors/enrollment-tokens', 'POST'),
  revokeSensor: (id: string) => request<AgentSensorSummary>(`/agent-sensors/${id}/revoke`, 'POST'),
  sessions: () => request<AgentSessionSummary[]>('/agent-sessions'),
  timeline: (id: string) => request<AgentTimelineEvent[]>(`/agent-sessions/${id}/timeline`),
  violations: (id: string) => request<AgentViolation[]>(`/agent-sessions/${id}/violations`),
  policies: () => request<AgentPolicySummary[]>('/agent-scope-policies'),
  createPolicy: (body: AgentPolicyBody) =>
    request<AgentPolicySummary>('/agent-scope-policies', 'POST', body),
  updatePolicy: (id: string, body: AgentPolicyBody) =>
    request<AgentPolicySummary>(`/agent-scope-policies/${id}`, 'PUT', body),
  deletePolicy: (id: string) => request<void>(`/agent-scope-policies/${id}`, 'DELETE'),
};
