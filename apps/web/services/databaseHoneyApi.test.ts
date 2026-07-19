// Purpose: verify the database honey API client sends auth headers, POSTs actions, targets
//   organization-scoped routes (never demo), and returns safe error messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSession, setSession } from './authSession';
import { DatabaseHoneyApiError, databaseHoneyApi } from './databaseHoneyApi';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('databaseHoneyApi', () => {
  it('lists connectors with org + key headers', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await databaseHoneyApi.connectors();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/database-connectors');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('POSTs lifecycle actions', async () => {
    connect();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'd', status: 'deploying' }), { status: 200 })),
    );
    await databaseHoneyApi.deploy('d1');
    const [url, init] = (fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls[0];
    expect(url).toBe('https://api.example.com/database-honey-deployments/d1/deploy');
    expect((init as { method: string }).method).toBe('POST');
  });

  it('maps 403 and 409 to safe messages', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 403 })));
    await expect(databaseHoneyApi.approve('d1')).rejects.toMatchObject({ status: 403 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('conflict', { status: 409 })));
    await expect(databaseHoneyApi.deploy('d1')).rejects.toMatchObject({ status: 409 });
  });

  it('throws when not connected', async () => {
    await expect(databaseHoneyApi.connectors()).rejects.toBeInstanceOf(DatabaseHoneyApiError);
  });
});
