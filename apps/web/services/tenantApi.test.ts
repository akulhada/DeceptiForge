// Purpose: verify the tenant API client sends auth headers and never calls demo routes.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSession, setSession } from './authSession';
import { tenantApi } from './tenantApi';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

describe('tenantApi', () => {
  it('sends organization and API-key headers to organization-scoped routes', async () => {
    setSession({
      baseUrl: 'https://api.example.com',
      organizationId: 'org-123',
      apiKey: 'dfk_secret',
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ organization_id: 'org-123', role: 'viewer', scopes: [] }), {
          status: 200,
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await tenantApi.whoami();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/whoami');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-123');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('throws when not connected', async () => {
    await expect(tenantApi.whoami()).rejects.toThrow();
  });
});
