// Purpose: verify the deployments API client sends auth headers, POSTs lifecycle actions, targets
//   organization-scoped routes (never demo), and returns safe error messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSession, setSession } from './authSession';
import { DeploymentApiError, deploymentsApi } from './deploymentsApi';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('deploymentsApi', () => {
  it('lists with org + key headers on an organization-scoped route', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await deploymentsApi.list();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/decoy-deployments');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('POSTs lifecycle actions', async () => {
    connect();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'd', status: 'approved' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await deploymentsApi.approve('d1');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/decoy-deployments/d1/approve');
    expect(init.method).toBe('POST');
  });

  it('maps 403 to a safe authorization message', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 403 })));
    await expect(deploymentsApi.deploy('d1')).rejects.toMatchObject({
      message: 'You are not authorized to perform this action.',
      status: 403,
    });
  });

  it('maps 409 to a safe state-conflict message', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('conflict', { status: 409 })));
    await expect(deploymentsApi.deploy('d1')).rejects.toMatchObject({ status: 409 });
  });

  it('throws when not connected', async () => {
    await expect(deploymentsApi.list()).rejects.toBeInstanceOf(DeploymentApiError);
  });
});
