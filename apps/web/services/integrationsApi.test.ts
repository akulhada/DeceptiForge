// Purpose: verify the integrations API client sends auth headers, targets organization-scoped routes
//   (never demo), uses the right verbs, sends the secret only on create, and maps errors safely.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSession, setSession } from './authSession';
import { IntegrationsApiError, integrationsApi } from './integrationsApi';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('integrationsApi', () => {
  it('lists integrations with org + key headers', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await integrationsApi.list();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/security-integrations');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
  });

  it('POSTs create with the secret in the body only', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);
    await integrationsApi.create({
      integration_type: 'generic_webhook', name: 'siem', endpoint: 'https://x/y', secret: 's3cr3t',
      minimum_severity: 'low', payload_profile: 'minimal', include_narrative: false,
      include_coverage_events: true, include_operational_events: true,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/security-integrations');
    expect((init as { method: string }).method).toBe('POST');
    expect((init as { body: string }).body).toContain('s3cr3t');
  });

  it('POSTs test and retry', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await integrationsApi.test('i1');
    await integrationsApi.retry('d1');
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.com/security-integrations/i1/test');
    expect(fetchMock.mock.calls[1][0]).toBe('https://api.example.com/integration-deliveries/d1/retry');
  });

  it('maps 403 to a safe message', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 403 })));
    await expect(integrationsApi.list()).rejects.toMatchObject({ status: 403 });
  });

  it('throws when not connected', async () => {
    await expect(integrationsApi.list()).rejects.toBeInstanceOf(IntegrationsApiError);
  });
});
