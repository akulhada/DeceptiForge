// Purpose: AI Agent Sensors admin panel — sensors, scope policies, sessions with a decoy-aware
//   timeline, and deterministic scope-violation explanations.
// Responsibilities: show sensor status/version/last-seen/stale, create enrollment tokens, edit
//   scope policies (allowed/denied paths), list sessions and their requested-vs-observed scope, and
//   render the minimized event timeline with path-class + decoy-touch + violation badges and the
//   deterministic explanation. Renders only minimized metadata — never prompts, source, or command
//   output. Dependencies: api, permissions, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { AgentSensorApiError, agentSensorApi } from '@/services/agentSensorApi';
import type {
  AgentPolicySummary,
  AgentSensorSummary,
  AgentSessionSummary,
  AgentTimelineEvent,
  AgentViolation,
} from '@/services/agentSensorTypes';
import {
  canManagePolicies,
  canManageSensors,
  isDecoyTouch,
  isStale,
  pathClassTone,
  severityTone,
  statusTone,
  violationLabel,
} from '@/services/agentSensorPermissions';

export function AgentSensorPanel({ scopes }: { scopes: readonly string[] }) {
  const [sensors, setSensors] = useState<AgentSensorSummary[] | null>(null);
  const [sessions, setSessions] = useState<AgentSessionSummary[] | null>(null);
  const [policies, setPolicies] = useState<AgentPolicySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<AgentTimelineEvent[] | null>(null);
  const [violations, setViolations] = useState<AgentViolation[] | null>(null);
  const [newPolicy, setNewPolicy] = useState('');
  const [allowed, setAllowed] = useState('');

  const refresh = useCallback(async () => {
    try {
      setSensors(await agentSensorApi.sensors());
      setSessions(await agentSensorApi.sessions().catch(() => []));
      setPolicies(await agentSensorApi.policies().catch(() => []));
      setError(null);
    } catch (err) {
      setError(err instanceof AgentSensorApiError ? err.message : 'Failed to load.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createToken = useCallback(async () => {
    setBusy('token');
    try {
      setToken((await agentSensorApi.createEnrollmentToken()).token);
      setError(null);
    } catch (err) {
      setError(err instanceof AgentSensorApiError ? err.message : 'Failed to create token.');
    } finally {
      setBusy(null);
    }
  }, []);

  const openSession = useCallback(async (id: string) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setTimeline(null);
    setViolations(null);
    setTimeline(await agentSensorApi.timeline(id).catch(() => []));
    setViolations(await agentSensorApi.violations(id).catch(() => []));
  }, [openId]);

  const revoke = useCallback(
    async (id: string) => {
      if (!window.confirm('Revoke this agent sensor? It can no longer report.')) return;
      setBusy(id);
      try {
        await agentSensorApi.revokeSensor(id);
        await refresh();
      } catch (err) {
        setError(err instanceof AgentSensorApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const savePolicy = useCallback(async () => {
    setBusy('policy');
    try {
      await agentSensorApi.createPolicy({
        name: newPolicy || 'scope-policy',
        allowed_paths: allowed.split(',').map((s) => s.trim()).filter(Boolean),
        denied_paths: [], allowed_tools: [], denied_tools: [], allowed_resource_types: [],
        maximum_file_reads: 200, maximum_sensitive_reads: 0, allow_dependency_changes: false,
        allow_secret_file_access: false, allow_database_access: false, allow_network_access: false,
      });
      setNewPolicy('');
      setAllowed('');
      await refresh();
    } catch (err) {
      setError(err instanceof AgentSensorApiError ? err.message : 'Failed to save policy.');
    } finally {
      setBusy(null);
    }
  }, [newPolicy, allowed, refresh]);

  if (sensors === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading agent sensors…</Card>;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Agent sensors (scope violations)</h2>
        <div className="flex gap-2">
          {canManageSensors(scopes) && (
            <Button onClick={() => void createToken()} disabled={busy !== null}>
              {busy === 'token' ? '…' : 'New enrollment token'}
            </Button>
          )}
          <Button variant="secondary" onClick={() => void refresh()}>
            Refresh
          </Button>
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {token && (
        <Card className="space-y-1 p-3 text-sm">
          <p className="font-semibold">One-time enrollment token (shown once)</p>
          <p className="font-mono break-all">{token}</p>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        Detect-only. Sensors report minimized activity metadata; file content, prompts, command
        output, and model reasoning are never captured. Scope violations are deterministic.
      </p>

      {sensors?.map((s) => (
        <Card key={s.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <Badge tone={statusTone(s.status)}>{s.status}</Badge>
          {isStale(s) && <Badge tone="warning">stale</Badge>}
          <span className="font-mono">{s.sensor_public_id}</span>
          <span className="text-muted-foreground">
            {s.name} · {s.adapter_type} · v{s.version}
          </span>
          {canManageSensors(scopes) && s.status !== 'revoked' && (
            <Button
              variant="primary"
              className="ml-auto"
              disabled={busy !== null}
              onClick={() => void revoke(s.id)}
            >
              {busy === s.id ? '…' : 'Revoke'}
            </Button>
          )}
        </Card>
      ))}

      {canManagePolicies(scopes) && (
        <Card className="space-y-2 p-4 text-sm">
          <h3 className="font-semibold">New scope policy</h3>
          <div className="flex flex-wrap gap-2">
            <input
              className="rounded border px-2 py-1 text-xs"
              placeholder="policy name"
              value={newPolicy}
              onChange={(e) => setNewPolicy(e.target.value)}
            />
            <input
              className="flex-1 rounded border px-2 py-1 font-mono text-xs"
              placeholder="allowed paths, comma-separated e.g. apps/web/**"
              value={allowed}
              onChange={(e) => setAllowed(e.target.value)}
            />
            <Button disabled={busy !== null} onClick={() => void savePolicy()}>
              {busy === 'policy' ? '…' : 'Create'}
            </Button>
          </div>
          {policies?.map((p) => (
            <div key={p.id} className="text-xs text-muted-foreground">
              {p.name} v{p.policy_version} · allow {p.allowed_paths.join(', ') || '—'}
            </div>
          ))}
        </Card>
      )}

      <h3 className="text-sm font-semibold">Sessions</h3>
      {sessions?.length === 0 && (
        <Card className="p-4 text-sm text-muted-foreground">No agent sessions yet.</Card>
      )}
      {sessions?.map((sess) => (
        <Card key={sess.id} className="space-y-2 p-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={sess.status === 'active' ? 'info' : 'success'}>{sess.status}</Badge>
            <span className="font-mono text-xs">{sess.agent_type}</span>
            <span className="text-muted-foreground">
              requested scope: {sess.task_summary_sanitized || '—'}
            </span>
            <Button variant="secondary" className="ml-auto" onClick={() => void openSession(sess.id)}>
              {openId === sess.id ? 'Hide' : 'Timeline & violations'}
            </Button>
          </div>

          {openId === sess.id && (
            <div className="space-y-3">
              {violations && violations.length > 0 && (
                <div className="space-y-1 rounded-md border p-3 text-xs">
                  <p className="font-semibold">Scope violations (deterministic)</p>
                  {violations.map((v) => (
                    <div key={v.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
                      <Badge tone={severityTone(v.severity)}>{v.severity}</Badge>
                      <span className="font-mono">{violationLabel(v)}</span>
                      <span className="text-muted-foreground">
                        {v.explanation} (rule: {v.policy_rule}, conf {v.confidence})
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <div className="space-y-1 rounded-md border p-3 text-xs">
                <p className="font-semibold">Observed activity (minimized)</p>
                {timeline === null && <p className="text-muted-foreground">Loading…</p>}
                {timeline?.length === 0 && <p className="text-muted-foreground">No events.</p>}
                {timeline?.map((e) => (
                  <div key={e.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
                    {e.path_class && <Badge tone={pathClassTone(e.path_class)}>{e.path_class}</Badge>}
                    {isDecoyTouch(e) && <Badge tone="danger">decoy touch</Badge>}
                    <span className="font-mono">{e.event_type}</span>
                    <span className="text-muted-foreground">
                      {e.normalized_path ?? e.tool_name ?? e.resource_type ?? '—'} ·{' '}
                      {e.observed_at.slice(0, 19)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      ))}
    </section>
  );
}
