// Purpose: Database honey records dashboard — connectors, deployments, masked preview, and actions.
// Responsibilities: show connector status/schema-sync, deployment status/monitoring/drift, a masked
//   row preview with the exact delete predicate, and permitted-only lifecycle actions with
//   confirmations and safe errors. Never renders passwords or unmasked sensitive values.
// Dependencies: api, permissions helper, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { databaseHoneyApi, DatabaseHoneyApiError } from '@/services/databaseHoneyApi';
import type {
  ConnectorSummary,
  HoneyDeploymentSummary,
  HoneyPreview,
} from '@/services/databaseHoneyTypes';
import {
  availableActions,
  isDrift,
  isTerminal,
  monitoringLabel,
  type HoneyAction,
} from '@/services/databaseHoneyPermissions';

const ACTION_LABEL: Record<HoneyAction, string> = {
  submit: 'Submit for approval',
  approve: 'Approve',
  reject: 'Reject',
  deploy: 'Deploy',
  retire: 'Retire',
  rollback: 'Roll back',
};

const IRREVERSIBLE: ReadonlySet<HoneyAction> = new Set(['deploy', 'retire', 'rollback', 'reject']);

function statusTone(status: string): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'deployed') return 'success';
  if (status.includes('fail') || status === 'rejected' || status === 'drift_detected') return 'danger';
  if (status.includes('ing') || status.includes('pending')) return 'warning';
  return 'info';
}

export function DatabaseHoneyPanel({ scopes }: { scopes: readonly string[] }) {
  const [connectors, setConnectors] = useState<ConnectorSummary[] | null>(null);
  const [items, setItems] = useState<HoneyDeploymentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [preview, setPreview] = useState<HoneyPreview | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConnectors(await databaseHoneyApi.connectors());
      setItems(await databaseHoneyApi.deployments());
      setError(null);
    } catch (err) {
      setError(err instanceof DatabaseHoneyApiError ? err.message : 'Failed to load.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openPreview = useCallback(async (id: string) => {
    setOpenId(id);
    setPreview(null);
    try {
      setPreview(await databaseHoneyApi.preview(id));
    } catch {
      setPreview(null);
    }
  }, []);

  const act = useCallback(
    async (id: string, action: HoneyAction) => {
      if (IRREVERSIBLE.has(action)) {
        const ok = window.confirm(`${ACTION_LABEL[action]} this honey deployment? This cannot be undone.`);
        if (!ok) return;
      }
      setBusy(`${id}:${action}`);
      try {
        await databaseHoneyApi[action](id);
        await refresh();
        setError(null);
      } catch (err) {
        setError(err instanceof DatabaseHoneyApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  if (items === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading database honey records…</Card>;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Database honey records</h2>
        <Button onClick={() => void refresh()} variant="secondary">
          Refresh
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {connectors?.map((conn) => (
        <Card key={conn.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <Badge tone={conn.status === 'active' ? 'success' : 'info'}>{conn.status}</Badge>
          <span className="font-mono">{conn.name}</span>
          <span className="text-muted-foreground">{conn.database_name} · ssl {conn.ssl_mode}</span>
          <span className="text-xs text-muted-foreground">
            {conn.last_schema_sync_at ? `synced ${conn.last_schema_sync_at.slice(0, 10)}` : 'not synced'}
          </span>
          {conn.safe_error_code && <span className="text-red-600">error: {conn.safe_error_code}</span>}
        </Card>
      ))}

      {items?.length === 0 && (
        <Card className="p-4 text-sm text-muted-foreground">No honey deployments yet.</Card>
      )}
      {items?.map((d) => {
        const actions = availableActions(d.status, scopes);
        return (
          <Card key={d.id} className="space-y-2 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(d.status)}>{d.status}</Badge>
              <span className="font-mono text-xs text-muted-foreground">
                {d.target_schema}.{d.target_table} · {d.decoy_type}
              </span>
              <Badge tone={d.monitoring_activated ? 'success' : 'info'}>
                monitoring: {monitoringLabel(d)}
              </Badge>
            </div>

            {isDrift(d.status) && (
              <p className="text-sm text-red-600">
                ⚠ The owned row changed unexpectedly. Automatic deletion is blocked; manual review is
                required before retiring or rolling back.
              </p>
            )}
            {d.safe_failure_message && (
              <p className="text-sm text-red-600">{d.safe_failure_message}</p>
            )}
            {d.expires_at && (
              <p className="text-xs text-muted-foreground">Expires {d.expires_at.slice(0, 10)}</p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => void openPreview(d.id)}>
                {openId === d.id ? 'Hide preview' : 'View preview'}
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

            {openId === d.id && preview && (
              <div className="space-y-2 rounded-md border p-3 text-xs">
                <p className="text-muted-foreground">{preview.verification_plan}</p>
                <p className="text-muted-foreground">{preview.delete_predicate}</p>
                {preview.warnings.map((w) => (
                  <p key={w} className="text-amber-600">
                    ⚠ {w}
                  </p>
                ))}
                <table className="w-full">
                  <tbody>
                    {preview.columns.map((col) => (
                      <tr key={col}>
                        <td className="pr-3 font-mono">{col}</td>
                        <td className="font-mono text-muted-foreground">
                          {preview.masked_values[col]}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        );
      })}
    </section>
  );
}
