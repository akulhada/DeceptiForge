// Purpose: verify the analysis-lab client sends auth headers to org-scoped routes (never /demo),
//   posts the request contract, maps documented status codes to safe messages, exposes Retry-After,
//   and flags schema mismatches.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AnalysisApiError, listScenarios, runPreview } from './analysisLabApi';
import { clearSession, setSession } from './authSession';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

const OK = {
  schema_version: 'analysis-preview-v1',
  organization_id: 'org-1',
  request_id: 'req-1',
  scenario_id: null,
  input_summary: {},
  context_profile: {},
  vocabulary: {},
  sensitive_zones: [],
  placement_recommendations: [],
  warnings: [],
  confidence: {},
  engine_versions: {},
  generated_at: '2026-01-01T00:00:00Z',
  stage_timings_ms: {},
};

describe('analysisLabApi', () => {
  it('lists scenarios with org + key headers on the org-scoped route', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await listScenarios();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/api/v1/analysis/scenarios');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('POSTs the signals contract and returns the response', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(OK), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const { response, schemaMismatch } = await runPreview({ languages: [{ name: 'Go' }] }, {
      scenarioId: 'fintech-payments',
    });
    expect(schemaMismatch).toBe(false);
    expect(response.request_id).toBe('req-1');
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body);
    expect(body.scenario_id).toBe('fintech-payments');
    expect(body.signals.languages[0].name).toBe('Go');
  });

  it('flags a schema mismatch', async () => {
    connect();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ...OK, schema_version: 'v2' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const { schemaMismatch } = await runPreview({});
    expect(schemaMismatch).toBe(true);
  });

  it.each([
    [401, 'authenticated'],
    [403, 'permitted'],
    [413, 'too large'],
    [422, 'validation'],
    [429, 'Rate limit'],
  ])('maps %i to a safe message', async (status, fragment) => {
    connect();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Input failed contract validation.' }), { status }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(runPreview({})).rejects.toThrow(AnalysisApiError);
    await expect(runPreview({})).rejects.toThrow(fragment);
  });

  it('exposes Retry-After on 429', async () => {
    connect();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('{}', { status: 429, headers: { 'Retry-After': '60' } }));
    vi.stubGlobal('fetch', fetchMock);
    try {
      await runPreview({});
      throw new Error('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(AnalysisApiError);
      expect((e as AnalysisApiError).retryAfterSeconds).toBe(60);
    }
  });

  it('rejects when not connected', async () => {
    await expect(runPreview({})).rejects.toThrow('Not connected');
  });
});
