// Purpose: Decoy Deployments dashboard — list, preview/diff, and permitted lifecycle actions.
// Responsibilities: show deployment status, repository, PR link, monitoring activation, expiry, and
//   safety warnings; expose submit/approve/reject/deploy/retire/rollback only when the viewer's
//   scopes and the state machine allow; confirm irreversible actions; surface stale-preview
//   warnings, loading, and safe error messages. Never renders secrets. Dependencies: api, helpers.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { deploymentsApi, DeploymentApiError } from '@/services/deploymentsApi';
import type {
  DeploymentPreview,
  DeploymentSummary,
} from '@/services/deploymentTypes';
import {
  availableActions,
  isPreviewStale,
  isTerminal,
  monitoringLabel,
  type DeploymentAction,
} from '@/services/deploymentPermissions';
import { DeploymentDiff } from './DeploymentDiff';

const ACTION_LABEL: Record<DeploymentAction, string> = {
  submit: 'Submit for approval',
  approve: 'Approve',
  reject: 'Reject',
  deploy: 'Deploy',
  retire: 'Retire',
  rollback: 'Roll back',
};

const IRREVERSIBLE: ReadonlySet<DeploymentAction> = new Set(['deploy', 'retire', 'rollback', 'reject']);

function statusTone(status: string): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'deployed') return 'success';
  if (status.includes('fail') || status === 'rejected' || status === 'cancelled') return 'danger';
  if (isPreviewStale(status as never) || status.includes('pending') || status.includes('ing')) {
    return 'warning';
  }
  return 'info';
}

export function DeploymentsPanel({ scopes }: { scopes: readonly string[] }) {
  const [items, setItems] = useState<DeploymentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [preview, setPreview] = useState<DeploymentPreview | null>(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await deploymentsApi.list());
      setError(null);
    } catch (err) {
      setError(err instanceof DeploymentApiError ? err.message : 'Failed to load deployments.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openPreview = useCallback(async (id: string) => {
    setOpenId(id);
    setPreview(null);
    try {
      setPreview(await deploymentsApi.preview(id));
    } catch {
      setPreview(null);
    }
  }, []);

  const act = useCallback(
    async (id: string, action: DeploymentAction) => {
      if (IRREVERSIBLE.has(action)) {
        const ok = window.confirm(`${ACTION_LABEL[action]} this deployment? This cannot be undone.`);
        if (!ok) return;
      }
      setBusy(`${id}:${action}`);
      try {
        await deploymentsApi[action](id);
        await refresh();
        setError(null);
      } catch (err) {
        setError(err instanceof DeploymentApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  if (items === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading deployments…</Card>;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Decoy deployments</h2>
        <Button onClick={() => void refresh()} variant="secondary">
          Refresh
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {items?.length === 0 && (
        <Card className="p-4 text-sm text-muted-foreground">No deployments yet.</Card>
      )}
      {items?.map((d) => {
        const actions = availableActions(d.status, scopes);
        return (
          <Card key={d.id} className="space-y-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={statusTone(d.status)}>{d.status}</Badge>
                <span className="font-mono text-xs text-muted-foreground">
                  repo {d.repository_id.slice(0, 8)} · {d.target_branch}
                </span>
                <Badge tone={d.monitoring_activated ? 'success' : 'info'}>
                  monitoring: {monitoringLabel(d)}
                </Badge>
              </div>
              {d.pull_request_url && (
                <a
                  className="text-sm text-sky-600 underline"
                  href={d.pull_request_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  PR #{d.pull_request_number}
                </a>
              )}
            </div>

            {isPreviewStale(d.status) && (
              <p className="text-sm text-amber-600">
                ⚠ The repository changed since this preview. Re-approval is required before deploying.
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
                {openId === d.id ? 'Hide diff' : 'View diff'}
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
              <div className="space-y-2 pt-2">
                <p className="text-xs text-muted-foreground">{preview.blast_radius}</p>
                {preview.warnings.map((w) => (
                  <p key={w} className="text-xs text-amber-600">
                    ⚠ {w}
                  </p>
                ))}
                {preview.items.map((item) => (
                  <DeploymentDiff key={item.decoy_id} item={item} />
                ))}
              </div>
            )}
          </Card>
        );
      })}
    </section>
  );
}
