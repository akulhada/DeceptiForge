// Purpose: verify the coverage API client sends auth headers, targets organization-scoped routes
//   (never demo), uses the right verbs, and maps errors to safe messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CoverageApiError, coverageApi } from './coverageApi';
import { clearSession, setSession } from './authSession';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('coverageApi', () => {
  it('reads coverage status with org + key headers', async () => {
    connect();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ status: 'no_snapshot' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await coverageApi.status();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/coverage');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('POSTs recalculate and recommendation actions', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await coverageApi.recalculate();
    await coverageApi.acceptRecommendation('r1');
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.com/coverage/recalculate');
    expect((fetchMock.mock.calls[0][1] as { method: string }).method).toBe('POST');
    expect(fetchMock.mock.calls[1][0]).toBe(
      'https://api.example.com/coverage/recommendations/r1/accept',
    );
  });

  it('maps 403 to a safe message', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 403 })));
    await expect(coverageApi.recalculate()).rejects.toMatchObject({ status: 403 });
  });

  it('throws when not connected', async () => {
    await expect(coverageApi.status()).rejects.toBeInstanceOf(CoverageApiError);
  });
});
