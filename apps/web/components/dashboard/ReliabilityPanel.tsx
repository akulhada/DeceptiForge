// Purpose: Reliability / disaster-recovery admin panel.
// Responsibilities: show the active region + failover state, dependency health (degraded flags),
//   latest verified restore + measured RPO/RTO against targets, restore-drill history, and failover
//   events with request/approve controls (separation of duties enforced server-side). Renders only
//   safe operational status — never infrastructure credentials or provider payloads. Dependencies:
//   api, permissions, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ReliabilityApiError, reliabilityApi } from '@/services/reliabilityApi';
import type {
  DependencyStatus,
  FailoverEvent,
  ReliabilityStatus,
  RestoreDrill,
} from '@/services/reliabilityTypes';
import {
  canApproveFailover,
  canRequestFailover,
  dependencyTone,
  failoverTone,
  isDegraded,
  restoreIsStale,
  withinCriticalTargets,
} from '@/services/reliabilityPermissions';

export function ReliabilityPanel({ scopes }: { scopes: readonly string[] }) {
  const [status, setStatus] = useState<ReliabilityStatus | null>(null);
  const [deps, setDeps] = useState<DependencyStatus | null>(null);
  const [drills, setDrills] = useState<RestoreDrill[]>([]);
  const [events, setEvents] = useState<FailoverEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await reliabilityApi.status());
      setDeps(await reliabilityApi.dependencies().catch(() => null));
      setDrills(await reliabilityApi.drills().catch(() => []));
      setEvents(await reliabilityApi.failoverEvents().catch(() => []));
      setError(null);
    } catch (err) {
      setError(err instanceof ReliabilityApiError ? err.message : 'Failed to load.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const failover = useCallback(
    async (action: 'request' | 'approve') => {
      const reason = window.prompt(`Reason for failover ${action}?`);
      if (!reason) return;
      if (
        action === 'request' &&
        !window.confirm('Request a regional failover? This begins a declared disaster procedure.')
      ) {
        return;
      }
      setBusy(action);
      try {
        if (action === 'request') await reliabilityApi.requestFailover(reason);
        else await reliabilityApi.approveFailover(reason);
        await refresh();
      } catch (err) {
        setError(err instanceof ReliabilityApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  if (status === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading reliability…</Card>;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Reliability &amp; disaster recovery</h2>
        <Button variant="secondary" onClick={() => void refresh()}>
          Refresh
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {status && (
        <Card className="space-y-2 p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="info">{status.region.role}</Badge>
            <Badge tone={failoverTone(status.failover_state)}>{status.failover_state}</Badge>
            <span className="font-mono text-xs">
              {status.region.deployment_region} · epoch {status.region.active_region_epoch}
            </span>
            {status.maintenance_mode && <Badge tone="warning">maintenance</Badge>}
            {status.region.dr_enabled && status.region.secondary_region && (
              <span className="text-xs text-muted-foreground">
                standby: {status.region.secondary_region}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {status.latest_verified_restore ? (
              <>
                latest verified restore: {status.latest_verified_restore.passed ? '✓' : '✗'}{' '}
                RPO {status.latest_verified_restore.achieved_rpo_minutes ?? '—'}m / RTO{' '}
                {status.latest_verified_restore.achieved_rto_minutes ?? '—'}m ·{' '}
                {status.latest_verified_restore.created_at.slice(0, 19)}
                {restoreIsStale(status.latest_verified_restore) && (
                  <span className="text-amber-600"> · drill overdue</span>
                )}
                {!withinCriticalTargets(status) && (
                  <span className="text-red-600"> · outside RPO/RTO targets</span>
                )}
              </>
            ) : (
              <span className="text-amber-600">
                No verified restore yet — a backup is not valid until restored.
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Critical target: RPO ≤ {status.recovery_objectives['critical']?.rpo_minutes}m, RTO ≤{' '}
            {status.recovery_objectives['critical']?.rto_minutes}m.
          </p>
        </Card>
      )}

      {deps && (
        <Card className="flex flex-wrap items-center gap-2 p-3 text-xs">
          <span className="font-semibold">Dependencies</span>
          {isDegraded(deps) && <Badge tone="danger">degraded</Badge>}
          <Badge tone={dependencyTone(deps.database.status)}>db: {deps.database.status}</Badge>
          <Badge tone={dependencyTone(deps.encryption.status)}>
            encryption: {deps.encryption.status}
          </Badge>
          <Badge tone={dependencyTone(deps.redis.status)}>redis: {deps.redis.status}</Badge>
          <Badge
            tone={
              deps.replay_protection.required
                ? dependencyTone(deps.replay_protection.status)
                : 'info'
            }
          >
            replay: {deps.replay_protection.required ? deps.replay_protection.status : 'optional'}
          </Badge>
        </Card>
      )}

      {(canRequestFailover(scopes) || canApproveFailover(scopes)) && (
        <Card className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <span className="font-semibold">Controlled failover</span>
          {canRequestFailover(scopes) && (
            <Button variant="primary" disabled={busy !== null} onClick={() => void failover('request')}>
              {busy === 'request' ? '…' : 'Request failover'}
            </Button>
          )}
          {canApproveFailover(scopes) && (
            <Button variant="secondary" disabled={busy !== null} onClick={() => void failover('approve')}>
              {busy === 'approve' ? '…' : 'Approve failover'}
            </Button>
          )}
          <span className="text-xs text-muted-foreground">
            A request and its approval must come from different operators.
          </span>
        </Card>
      )}

      {drills.length > 0 && (
        <Card className="space-y-1 p-4 text-xs">
          <p className="text-sm font-semibold">Restore drills</p>
          {drills.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
              <Badge tone={d.passed ? 'success' : 'danger'}>{d.passed ? 'passed' : 'failed'}</Badge>
              <span className="font-mono">{d.backup_identifier}</span>
              <span className="text-muted-foreground">
                RPO {d.achieved_rpo_minutes ?? '—'}m / RTO {d.achieved_rto_minutes ?? '—'}m ·{' '}
                {d.created_at.slice(0, 19)}
              </span>
            </div>
          ))}
        </Card>
      )}

      {events.length > 0 && (
        <Card className="space-y-1 p-4 text-xs">
          <p className="text-sm font-semibold">Failover events</p>
          {events.map((e) => (
            <div key={e.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
              <span className="font-mono">
                {e.from_state} → {e.to_state}
              </span>
              <span className="text-muted-foreground">
                {e.deployment_region} · epoch {e.active_region_epoch} · {e.created_at.slice(0, 19)} ·{' '}
                {e.reason}
              </span>
            </div>
          ))}
        </Card>
      )}
    </section>
  );
}
