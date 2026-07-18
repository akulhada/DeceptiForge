// Purpose: let a staging user connect the dashboard to an authenticated tenant API.
// Responsibilities: collect base URL, organization id, and API key, test them via /whoami, and store
//   them only in the session (never env). Clearly labeled as a staging API-key connection, not SSO.
'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { clearSession, setSession } from '@/services/authSession';
import { tenantApi, TenantApiError } from '@/services/tenantApi';

export function ConnectPanel({ onConnected }: { onConnected: () => void }) {
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000');
  const [organizationId, setOrganizationId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  const connect = async () => {
    setTesting(true);
    setError(null);
    setSession({ baseUrl: baseUrl.replace(/\/$/, ''), organizationId, apiKey });
    try {
      await tenantApi.whoami();
      onConnected();
    } catch (caught) {
      clearSession();
      setError(caught instanceof TenantApiError ? caught.message : 'Connection failed.');
    } finally {
      setTesting(false);
    }
  };

  const field = 'w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm';
  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader>
        <CardTitle>Connect to a tenant API</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="rounded-md border border-amber-900/60 bg-amber-950/30 p-2 text-xs text-amber-300">
          This is a staging API-key connection, not SSO. The key is kept only in this browser session.
        </p>
        <label className="block text-xs text-slate-400">
          API base URL
          <input className={field} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </label>
        <label className="block text-xs text-slate-400">
          Organization id
          <input
            className={field}
            value={organizationId}
            onChange={(e) => setOrganizationId(e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
          />
        </label>
        <label className="block text-xs text-slate-400">
          API key
          <input
            className={field}
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="dfk_…"
          />
        </label>
        {error ? <p className="text-xs text-red-300">{error}</p> : null}
        <Button onClick={() => void connect()} disabled={testing || !organizationId || !apiKey}>
          {testing ? 'Connecting…' : 'Connect'}
        </Button>
      </CardContent>
    </Card>
  );
}
