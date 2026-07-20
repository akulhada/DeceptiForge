// Purpose: SIEM/SOAR Integrations admin panel — configured integrations, delivery history, dead
//   letters, and a redacted payload preview.
// Responsibilities: list integrations (status/type/redacted endpoint/last success+failure), create
//   one (with a write-only secret field), test/disable, show delivery counts + recent deliveries +
//   dead letters with retry, and a redacted sample payload preview. Never renders secrets or full
//   endpoints with query strings. Dependencies: api, permissions, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { IntegrationsApiError, integrationsApi } from '@/services/integrationsApi';
import type {
  CreateIntegration,
  DeadLetter,
  Delivery,
  IntegrationSummary,
  IntegrationType,
} from '@/services/integrationsTypes';
import {
  canManage,
  canRetry,
  canTest,
  deliverySummary,
  deliveryTone,
  redactEndpoint,
  redactedSamplePayload,
  statusTone,
} from '@/services/integrationsPermissions';

const TYPES: IntegrationType[] = [
  'generic_webhook',
  'splunk_hec',
  'microsoft_sentinel',
  'elastic',
];

export function IntegrationsPanel({ scopes }: { scopes: readonly string[] }) {
  const [integrations, setIntegrations] = useState<IntegrationSummary[] | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [deadLetters, setDeadLetters] = useState<DeadLetter[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [form, setForm] = useState<CreateIntegration>({
    integration_type: 'generic_webhook', name: '', endpoint: '', secret: '',
    minimum_severity: 'low', payload_profile: 'minimal', include_narrative: false,
    include_coverage_events: true, include_operational_events: true,
  });

  const refresh = useCallback(async () => {
    try {
      setIntegrations(await integrationsApi.list());
      setDeliveries(await integrationsApi.deliveries().catch(() => []));
      setDeadLetters(await integrationsApi.deadLetters().catch(() => []));
      setError(null);
    } catch (err) {
      setError(err instanceof IntegrationsApiError ? err.message : 'Failed to load.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async () => {
    setBusy('create');
    try {
      await integrationsApi.create(form);
      setForm({ ...form, name: '', endpoint: '', secret: '' });
      await refresh();
    } catch (err) {
      setError(err instanceof IntegrationsApiError ? err.message : 'Create failed.');
    } finally {
      setBusy(null);
    }
  }, [form, refresh]);

  const act = useCallback(
    async (id: string, action: 'test' | 'disable') => {
      if (action === 'disable' && !window.confirm('Disable this integration?')) return;
      setBusy(`${id}:${action}`);
      try {
        if (action === 'test') {
          const res = await integrationsApi.test(id);
          window.alert(`Test ${res.ok ? 'succeeded' : 'failed'} (status: ${res.status})`);
        } else {
          await integrationsApi.disable(id);
        }
        await refresh();
      } catch (err) {
        setError(err instanceof IntegrationsApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const retry = useCallback(
    async (id: string) => {
      setBusy(`d:${id}`);
      try {
        await integrationsApi.retry(id);
        await refresh();
      } catch (err) {
        setError(err instanceof IntegrationsApiError ? err.message : 'Retry failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  if (integrations === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading integrations…</Card>;
  }

  const counts = deliverySummary(deliveries);

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">SIEM / SOAR integrations</h2>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {integrations?.length === 0 && (
        <Card className="p-4 text-sm text-muted-foreground">No integrations configured.</Card>
      )}
      {integrations?.map((i) => (
        <Card key={i.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <Badge tone={statusTone(i.status)}>{i.status}</Badge>
          <span className="font-mono">{i.integration_type}</span>
          <span>{i.name}</span>
          <span className="text-xs text-muted-foreground">{redactEndpoint(i.endpoint_reference)}</span>
          <span className="text-xs text-muted-foreground">
            profile {i.payload_profile} · min {i.minimum_severity}
            {i.last_success_at ? ` · ok ${i.last_success_at.slice(0, 19)}` : ''}
            {i.safe_failure_code ? ` · err ${i.safe_failure_code}` : ''}
          </span>
          <span className="ml-auto flex gap-1">
            <Button variant="secondary" onClick={() => setPreview(redactedSamplePayload(i))}>
              Preview
            </Button>
            {canTest(scopes) && (
              <Button variant="secondary" disabled={busy !== null} onClick={() => void act(i.id, 'test')}>
                {busy === `${i.id}:test` ? '…' : 'Test'}
              </Button>
            )}
            {canManage(scopes) && i.status !== 'revoked' && (
              <Button variant="primary" disabled={busy !== null} onClick={() => void act(i.id, 'disable')}>
                Disable
              </Button>
            )}
          </span>
        </Card>
      ))}

      {preview && (
        <Card className="space-y-1 p-3 text-xs">
          <p className="font-semibold">Redacted sample payload</p>
          <pre className="whitespace-pre-wrap font-mono text-muted-foreground">{preview}</pre>
        </Card>
      )}

      {canManage(scopes) && (
        <Card className="space-y-2 p-4 text-sm">
          <h3 className="font-semibold">New integration</h3>
          <div className="flex flex-wrap gap-2">
            <select
              className="rounded border px-2 py-1 text-xs"
              value={form.integration_type}
              onChange={(e) =>
                setForm({ ...form, integration_type: e.target.value as IntegrationType })
              }
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              className="rounded border px-2 py-1 text-xs"
              placeholder="name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="flex-1 rounded border px-2 py-1 font-mono text-xs"
              placeholder="https://siem.example.com/hook"
              value={form.endpoint}
              onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
            />
            <input
              className="rounded border px-2 py-1 text-xs"
              type="password"
              placeholder="secret / token (write-only)"
              value={form.secret ?? ''}
              onChange={(e) => setForm({ ...form, secret: e.target.value })}
            />
            <select
              className="rounded border px-2 py-1 text-xs"
              value={form.payload_profile}
              onChange={(e) => setForm({ ...form, payload_profile: e.target.value })}
            >
              {['minimal', 'standard', 'analyst', 'compliance_summary'].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <Button disabled={busy !== null || !form.name || !form.endpoint} onClick={() => void create()}>
              {busy === 'create' ? '…' : 'Create'}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Endpoints are SSRF-validated; the secret is stored encrypted and never returned.
          </p>
        </Card>
      )}

      <Card className="space-y-1 p-4 text-xs">
        <p className="text-sm font-semibold">Deliveries</p>
        <p className="text-muted-foreground">
          {Object.entries(counts).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'none'} · dead
          letters: {deadLetters.length}
        </p>
        {deliveries.slice(0, 10).map((d) => (
          <div key={d.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
            <Badge tone={deliveryTone(d.status)}>{d.status}</Badge>
            <span className="font-mono">{d.event_type}</span>
            <span className="text-muted-foreground">
              attempts {d.attempt_count}
              {d.response_status ? ` · http ${d.response_status}` : ''}
              {d.safe_error_code ? ` · ${d.safe_error_code}` : ''}
            </span>
            {canRetry(scopes) && d.status === 'dead_lettered' && (
              <Button
                variant="secondary"
                className="ml-auto"
                disabled={busy !== null}
                onClick={() => void retry(d.id)}
              >
                {busy === `d:${d.id}` ? '…' : 'Retry'}
              </Button>
            )}
          </div>
        ))}
      </Card>
    </section>
  );
}
