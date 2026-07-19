// Purpose: verify the AI tripwire API client sends auth headers, POSTs actions, targets
//   organization-scoped routes (never demo), and returns safe error messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AiTripwireApiError, aiTripwireApi } from './aiTripwireApi';
import { clearSession, setSession } from './authSession';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('aiTripwireApi', () => {
  it('lists RAG connectors with org + key headers', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await aiTripwireApi.ragConnectors();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/rag-connectors');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('GETs the minimized event timeline', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await aiTripwireApi.events('d1');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/ai-tripwire-deployments/d1/events');
    expect((init as { method: string }).method).toBe('GET');
  });

  it('POSTs lifecycle actions', async () => {
    connect();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: 'd', status: 'deploying' }), { status: 200 }),
      ),
    );
    await aiTripwireApi.deploy('d1');
    const [url, init] = (fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls[0];
    expect(url).toBe('https://api.example.com/ai-tripwire-deployments/d1/deploy');
    expect((init as { method: string }).method).toBe('POST');
  });

  it('maps 403 and 409 to safe messages', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 403 })));
    await expect(aiTripwireApi.approve('d1')).rejects.toMatchObject({ status: 403 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('conflict', { status: 409 })));
    await expect(aiTripwireApi.deploy('d1')).rejects.toMatchObject({ status: 409 });
  });

  it('throws when not connected', async () => {
    await expect(aiTripwireApi.ragConnectors()).rejects.toBeInstanceOf(AiTripwireApiError);
  });
});
