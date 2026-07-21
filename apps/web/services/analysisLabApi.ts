// Purpose: authenticated client for the Interactive Demo Lab preview endpoints.
// Responsibilities: send organization/API-key headers to the org-scoped analysis routes, map each
//   documented status code (401/403/413/422/429/500) to a safe message, and surface schema-version
//   mismatches. Never stores input or results. Dependencies: session, contract types.
'use client';

import { getSession } from './authSession';
import { SCHEMA_VERSION } from './analysisLabTypes';
import type {
  AnalysisOptions,
  AnalysisPreviewResponse,
  ScenarioSummary,
} from './analysisLabTypes';

export class AnalysisApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = 'AnalysisApiError';
  }
}

export interface PreviewResult {
  response: AnalysisPreviewResponse;
  schemaMismatch: boolean;
}

function messageForStatus(status: number, detail: string | undefined): string {
  switch (status) {
    case 401:
      return 'Not authenticated. Connect with a valid API key.';
    case 403:
      return 'Your role is not permitted to run analysis (needs analysis:preview).';
    case 413:
      return 'Input is too large. Reduce the number of signals and retry.';
    case 422:
      return detail ?? 'Input failed contract validation.';
    case 429:
      return 'Rate limit exceeded. Wait a moment and retry.';
    default:
      return detail ?? `Request failed (${status}).`;
  }
}

async function parseError(response: Response): Promise<never> {
  const payload: unknown = await response.json().catch(() => null);
  const detail =
    typeof payload === 'object' && payload !== null && 'detail' in payload &&
    typeof (payload as { detail: unknown }).detail === 'string'
      ? (payload as { detail: string }).detail
      : undefined;
  const retryHeader = response.headers.get('Retry-After');
  const retryAfter = retryHeader ? Number.parseInt(retryHeader, 10) : undefined;
  throw new AnalysisApiError(
    messageForStatus(response.status, detail),
    response.status,
    Number.isFinite(retryAfter) ? retryAfter : undefined,
  );
}

export async function listScenarios(): Promise<ScenarioSummary[]> {
  const session = getSession();
  if (!session) throw new AnalysisApiError('Not connected.', 0);
  let response: Response;
  try {
    response = await fetch(`${session.baseUrl}/api/v1/analysis/scenarios`, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'content-type': 'application/json',
        'X-DeceptiForge-Org-Id': session.organizationId,
        'X-DeceptiForge-API-Key': session.apiKey,
      },
    });
  } catch {
    throw new AnalysisApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (!response.ok) await parseError(response);
  return (await response.json()) as ScenarioSummary[];
}

export async function runPreview(
  signals: Record<string, unknown>,
  options?: { scenarioId?: string | null; options?: AnalysisOptions },
): Promise<PreviewResult> {
  const session = getSession();
  if (!session) throw new AnalysisApiError('Not connected.', 0);
  let response: Response;
  try {
    response = await fetch(`${session.baseUrl}/api/v1/analysis/preview`, {
      method: 'POST',
      cache: 'no-store',
      headers: {
        'content-type': 'application/json',
        'X-DeceptiForge-Org-Id': session.organizationId,
        'X-DeceptiForge-API-Key': session.apiKey,
      },
      body: JSON.stringify({
        signals,
        scenario_id: options?.scenarioId ?? null,
        options: options?.options,
      }),
    });
  } catch {
    throw new AnalysisApiError(`Cannot reach the API at ${session.baseUrl}.`, 0);
  }
  if (!response.ok) await parseError(response);
  const body = (await response.json()) as AnalysisPreviewResponse;
  return { response: body, schemaMismatch: body.schema_version !== SCHEMA_VERSION };
}
