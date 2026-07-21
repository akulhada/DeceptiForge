// Purpose: the judge workspace API client.
// Responsibilities: call /api/v1/judge/* with the session credential and turn every failure into a
//   typed access state, so the UI renders what is actually true rather than a generic error. Uses
//   the existing tenant session — the workspace deliberately introduces no second authentication
//   mechanism.
// Dependencies: authSession only.
'use client';

import { getSession } from './authSession';

/** Every state the workspace can be in. The UI switches on exactly these. */
export type AccessState =
  | 'loading'
  | 'unauthenticated'
  | 'no-organization'
  | 'forbidden'
  | 'expired'
  | 'quota-exceeded'
  | 'unavailable'
  | 'ready';

export class JudgeApiError extends Error {
  constructor(
    message: string,
    readonly state: AccessState,
    readonly retryAfterSeconds: number | null = null,
  ) {
    super(message);
    this.name = 'JudgeApiError';
  }
}

export interface Quota {
  used: number;
  limit: number;
  remaining: number;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
}

export interface Workspace {
  organization_id: string;
  session_id: string;
  environment: string;
  label: string;
  expires_at: string;
  quotas: Record<string, Quota>;
  scenarios: Scenario[];
}

export interface Interaction {
  trace_identifier: string;
  event_recorded: boolean;
  alert_id: string | null;
  incident_id: string | null;
  quotas: Record<string, Quota>;
}

export interface SandboxExport {
  organization_id: string;
  session_id: string;
  environment: string;
  exported_at: string;
  repositories: number;
  decoy_assets: number;
  monitoring_events: number;
  alerts: number;
  incidents: number;
  quotas: Record<string, Quota>;
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<T> {
  const session = getSession();
  if (!session) throw new JudgeApiError('No sandbox credential.', 'unauthenticated');
  if (!session.organizationId) {
    throw new JudgeApiError('No organization bound to this credential.', 'no-organization');
  }

  let response: Response;
  try {
    response = await fetch(`${session.baseUrl}/api/v1/judge${path}`, {
      method,
      cache: 'no-store',
      headers: {
        'content-type': 'application/json',
        'X-DeceptiForge-Org-Id': session.organizationId,
        'X-DeceptiForge-API-Key': session.apiKey,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new JudgeApiError(`Cannot reach the API at ${session.baseUrl}.`, 'unavailable');
  }

  if (response.status === 401) {
    throw new JudgeApiError('This sandbox credential was rejected.', 'unauthenticated');
  }
  if (response.status === 403) {
    // Authenticated, but without the judge scopes — a distinct state from "not signed in", and the
    // one a tenant credential lands in if it is pointed at this workspace.
    throw new JudgeApiError('This credential lacks judge permissions.', 'forbidden');
  }
  if (response.status === 404 || response.status === 410) {
    throw new JudgeApiError('This sandbox session has ended.', 'expired');
  }
  if (response.status === 429) {
    const header = response.headers.get('Retry-After');
    const retry = header ? Number.parseInt(header, 10) : Number.NaN;
    throw new JudgeApiError(
      await safeDetail(response, 'Sandbox quota exceeded.'),
      'quota-exceeded',
      Number.isFinite(retry) ? retry : null,
    );
  }
  if (!response.ok) {
    throw new JudgeApiError(await safeDetail(response, 'The workspace is unavailable.'), 'unavailable');
  }
  return (await response.json()) as T;
}

async function safeDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === 'string' ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export const judgeApi = {
  workspace: () => request<Workspace>('/workspace'),
  analyze: (signals: unknown, scenarioId?: string) =>
    request<unknown>('/analyze', 'POST', { signals, scenario_id: scenarioId ?? null }),
  interact: () => request<Interaction>('/interact', 'POST'),
  exportSandbox: () => request<SandboxExport>('/export'),
  reset: () => request<{ deleted: Record<string, number> }>('/reset', 'POST'),
};
