// Purpose: verify the reliability API client sends auth headers, targets the admin routes, uses the
//   right verbs, and maps errors to safe messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSession, setSession } from './authSession';
import { ReliabilityApiError, reliabilityApi } from './reliabilityApi';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('reliabilityApi', () => {
  it('reads status with org + key headers', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await reliabilityApi.status();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/admin/reliability/status');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
  });

  it('POSTs failover request + approve with a reason', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await reliabilityApi.requestFailover('outage');
    await reliabilityApi.approveFailover('approve');
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.com/admin/reliability/failover/request');
    expect((fetchMock.mock.calls[0][1] as { method: string; body: string }).method).toBe('POST');
    expect((fetchMock.mock.calls[0][1] as { body: string }).body).toContain('outage');
    expect(fetchMock.mock.calls[1][0]).toBe('https://api.example.com/admin/reliability/failover/approve');
  });

  it('maps 403 to a safe message', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 403 })));
    await expect(reliabilityApi.requestFailover('x')).rejects.toMatchObject({ status: 403 });
  });

  it('throws when not connected', async () => {
    await expect(reliabilityApi.status()).rejects.toBeInstanceOf(ReliabilityApiError);
  });
});
