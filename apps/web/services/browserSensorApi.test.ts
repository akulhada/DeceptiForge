// Purpose: verify the browser-sensor API client sends auth headers, targets organization-scoped
//   routes (never demo), uses the right verbs, and maps errors to safe messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSession, setSession } from './authSession';
import { BrowserSensorApiError, browserSensorApi } from './browserSensorApi';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('browserSensorApi', () => {
  it('lists sensors with org + key headers', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await browserSensorApi.sensors();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/browser-sensors');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('POSTs enrollment token creation', async () => {
    connect();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ token: 't', expires_at: '' }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);
    await browserSensorApi.createEnrollmentToken();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/browser-sensors/enrollment-tokens');
    expect((init as { method: string }).method).toBe('POST');
  });

  it('PUTs the policy update', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await browserSensorApi.updatePolicy({
      enabled: true,
      trace_match_mode: 'exact',
      local_only_mode: false,
      event_reporting_enabled: true,
      show_user_notification: true,
      allow_pause: true,
      min_extension_version: '0.1.0',
      rules: [{ domain: 'chatgpt.com', classification: 'shadow' }],
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/browser-ai-policy');
    expect((init as { method: string }).method).toBe('PUT');
    expect((init as { body: string }).body).toContain('chatgpt.com');
  });

  it('maps 403 and 409 to safe messages', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 403 })));
    await expect(browserSensorApi.revoke('s1')).rejects.toMatchObject({ status: 403 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 409 })));
    await expect(browserSensorApi.rotate('s1')).rejects.toMatchObject({ status: 409 });
  });

  it('throws when not connected', async () => {
    await expect(browserSensorApi.sensors()).rejects.toBeInstanceOf(BrowserSensorApiError);
  });
});
