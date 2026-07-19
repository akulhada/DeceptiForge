// Purpose: AI (RAG/MCP) tripwire dashboard — connectors, deployment lifecycle, exact inert preview,
//   and a minimized event timeline with AI-native exposure labels.
// Responsibilities: show connector health, deployment status/monitoring/drift, the exact deployed
//   content + trace mechanisms (clearly synthetic), permitted-only lifecycle actions with
//   confirmations, and the deterministic event evidence separated from any AI narrative. Renders
//   only minimized event metadata — never prompts, chunks, or model output. Dependencies: api,
//   permissions helper, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { AiTripwireApiError, aiTripwireApi } from '@/services/aiTripwireApi';
import type {
  McpConnectorSummary,
  RagConnectorSummary,
  TripwireEvent,
  TripwirePreview,
  TripwireSummary,
} from '@/services/aiTripwireTypes';
import {
  availableActions,
  exposureLabel,
  isDrift,
  isTerminal,
  monitoringLabel,
  surfaceLabel,
  type TripwireAction,
} from '@/services/aiTripwirePermissions';

const ACTION_LABEL: Record<TripwireAction, string> = {
  submit: 'Submit for approval',
  approve: 'Approve',
  reject: 'Reject',
  deploy: 'Deploy',
  retire: 'Retire',
};

const IRREVERSIBLE: ReadonlySet<TripwireAction> = new Set(['deploy', 'retire', 'reject']);

function statusTone(status: string): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'deployed') return 'success';
  if (status.includes('fail') || status === 'rejected' || status === 'drift_detected') return 'danger';
  if (status.includes('ing') || status.includes('pending')) return 'warning';
  return 'info';
}

export function AiTripwirePanel({ scopes }: { scopes: readonly string[] }) {
  const [rag, setRag] = useState<RagConnectorSummary[] | null>(null);
  const [mcp, setMcp] = useState<McpConnectorSummary[] | null>(null);
  const [items, setItems] = useState<TripwireSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [preview, setPreview] = useState<TripwirePreview | null>(null);
  const [events, setEvents] = useState<TripwireEvent[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRag(await aiTripwireApi.ragConnectors().catch(() => []));
      setMcp(await aiTripwireApi.mcpConnectors().catch(() => []));
      setItems(await aiTripwireApi.deployments());
      setError(null);
    } catch (err) {
      setError(err instanceof AiTripwireApiError ? err.message : 'Failed to load.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openDetail = useCallback(async (id: string) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setPreview(null);
    setEvents(null);
    try {
      setPreview(await aiTripwireApi.preview(id));
    } catch {
      setPreview(null);
    }
    try {
      setEvents(await aiTripwireApi.events(id));
    } catch {
      setEvents([]);
    }
  }, [openId]);

  const act = useCallback(
    async (id: string, action: TripwireAction) => {
      if (IRREVERSIBLE.has(action)) {
        const ok = window.confirm(`${ACTION_LABEL[action]} this tripwire? This cannot be undone.`);
        if (!ok) return;
      }
      setBusy(`${id}:${action}`);
      try {
        await aiTripwireApi[action](id);
        await refresh();
        setError(null);
      } catch (err) {
        setError(err instanceof AiTripwireApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  if (items === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading AI tripwires…</Card>;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">AI tripwires (RAG / MCP)</h2>
        <Button onClick={() => void refresh()} variant="secondary">
          Refresh
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {rag?.map((conn) => (
        <Card key={conn.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <Badge tone={conn.status === 'active' ? 'success' : 'info'}>{conn.status}</Badge>
          <span className="font-mono">{conn.name}</span>
          <span className="text-muted-foreground">
            RAG · {conn.connector_type} · {conn.index_or_collection}
          </span>
          {conn.safe_error_code && <span className="text-red-600">error: {conn.safe_error_code}</span>}
        </Card>
      ))}
      {mcp?.map((conn) => (
        <Card key={conn.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <Badge tone={conn.status === 'active' ? 'success' : 'info'}>{conn.status}</Badge>
          <span className="font-mono">{conn.name}</span>
          <span className="text-muted-foreground">MCP · {conn.transport_type} · {conn.server_reference}</span>
          {conn.safe_error_code && <span className="text-red-600">error: {conn.safe_error_code}</span>}
        </Card>
      ))}

      {items?.length === 0 && (
        <Card className="p-4 text-sm text-muted-foreground">No AI tripwires yet.</Card>
      )}
      {items?.map((d) => {
        const actions = availableActions(d.status, scopes);
        return (
          <Card key={d.id} className="space-y-2 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(d.status)}>{d.status}</Badge>
              <Badge tone="info">{surfaceLabel(d.surface_type)}</Badge>
              <span className="font-mono text-xs text-muted-foreground">
                {d.target_collection} · {d.decoy_kind} · trace {d.trace_id}
              </span>
              <Badge tone={d.monitoring_activated ? 'success' : 'info'}>
                monitoring: {monitoringLabel(d)}
              </Badge>
            </div>

            {isDrift(d.status) && (
              <p className="text-sm text-red-600">
                ⚠ The deployed asset changed unexpectedly. Automatic deletion is blocked; manual
                review is required before retiring.
              </p>
            )}
            {d.safe_failure_message && (
              <p className="text-sm text-red-600">{d.safe_failure_message}</p>
            )}
            {d.expires_at && (
              <p className="text-xs text-muted-foreground">Expires {d.expires_at.slice(0, 10)}</p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => void openDetail(d.id)}>
                {openId === d.id ? 'Hide detail' : 'View preview & events'}
              </Button>
              {actions.map((action) => (
                <Button
                  key={action}
                  variant={IRREVERSIBLE.has(action) ? 'primary' : 'secondary'}
                  disabled={busy !== null}
                  onClick={() => void act(d.id, action)}
                >
                  {busy === `${d.id}:${action}` ? '…' : ACTION_LABEL[action]}
                </Button>
              ))}
              {actions.length === 0 && !isTerminal(d.status) && (
                <span className="text-xs text-muted-foreground">No actions available to you.</span>
              )}
            </div>

            {openId === d.id && (
              <div className="space-y-3">
                {preview && (
                  <div className="space-y-2 rounded-md border p-3 text-xs">
                    <p className="font-semibold">Exact deployed content (inert, synthetic)</p>
                    <pre className="whitespace-pre-wrap font-mono text-muted-foreground">
                      {preview.exact_content}
                    </pre>
                    <p className="text-muted-foreground">
                      Trace mechanisms: {preview.trace_mechanisms.join('; ')}
                    </p>
                    <p className="text-muted-foreground">{preview.verification_plan}</p>
                    <p className="text-muted-foreground">{preview.retirement_plan}</p>
                  </div>
                )}
                <div className="space-y-2 rounded-md border p-3 text-xs">
                  <p className="font-semibold">Deterministic event evidence</p>
                  <p className="text-muted-foreground">
                    Only minimized, signed event metadata is stored. Prompts, retrieved chunks, and
                    model output are never captured.
                  </p>
                  {events === null && <p className="text-muted-foreground">Loading events…</p>}
                  {events?.length === 0 && <p className="text-muted-foreground">No events yet.</p>}
                  {events?.map((e) => (
                    <div key={e.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
                      <Badge tone="warning">{exposureLabel(e)}</Badge>
                      <span className="font-mono">{e.event_type}</span>
                      <span className="text-muted-foreground">
                        {e.observed_at.slice(0, 19)} · source {e.source_id} · monitor{' '}
                        {e.monitor_identity} · conf {e.confidence}
                      </span>
                      <span className="font-mono text-muted-foreground">{e.minimized_metadata}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </section>
  );
}
