// Purpose: verify the agent-sensor API client sends auth headers, targets organization-scoped
//   routes (never demo), uses the right verbs, and maps errors to safe messages.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AgentSensorApiError, agentSensorApi } from './agentSensorApi';
import { clearSession, setSession } from './authSession';

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

function connect() {
  setSession({ baseUrl: 'https://api.example.com', organizationId: 'org-1', apiKey: 'dfk_secret' });
}

describe('agentSensorApi', () => {
  it('lists sensors with org + key headers', async () => {
    connect();
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await agentSensorApi.sensors();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.com/agent-sensors');
    expect(url).not.toContain('/demo/');
    expect(init.headers['X-DeceptiForge-Org-Id']).toBe('org-1');
    expect(init.headers['X-DeceptiForge-API-Key']).toBe('dfk_secret');
  });

  it('GETs the session timeline and violations', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await agentSensorApi.timeline('s1');
    await agentSensorApi.violations('s1');
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.com/agent-sessions/s1/timeline');
    expect(fetchMock.mock.calls[1][0]).toBe('https://api.example.com/agent-sessions/s1/violations');
  });

  it('POSTs enrollment token and PUTs policy', async () => {
    connect();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await agentSensorApi.createEnrollmentToken();
    expect((fetchMock.mock.calls[0][1] as { method: string }).method).toBe('POST');
    await agentSensorApi.updatePolicy('p1', {
      name: 'x', allowed_paths: ['apps/web/**'], denied_paths: [], allowed_tools: [],
      denied_tools: [], allowed_resource_types: [], maximum_file_reads: 200,
      maximum_sensitive_reads: 0, allow_dependency_changes: false, allow_secret_file_access: false,
      allow_database_access: false, allow_network_access: false,
    });
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe('https://api.example.com/agent-scope-policies/p1');
    expect((init as { method: string }).method).toBe('PUT');
  });

  it('maps 403 and 409 to safe messages', async () => {
    connect();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 403 })));
    await expect(agentSensorApi.revokeSensor('s1')).rejects.toMatchObject({ status: 403 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 409 })));
    await expect(agentSensorApi.sessions()).rejects.toMatchObject({ status: 409 });
  });

  it('throws when not connected', async () => {
    await expect(agentSensorApi.sensors()).rejects.toBeInstanceOf(AgentSensorApiError);
  });
});
