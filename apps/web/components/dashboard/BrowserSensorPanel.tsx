// Purpose: Browser Sensors admin panel — enrolled sensors, enrollment tokens, approved/shadow AI
//   policy, and the minimized AI-paste event timeline.
// Responsibilities: show sensor status/version/last-seen/stale, create one-time enrollment tokens
//   (shown once), edit the approved/shadow domain policy, revoke/rotate sensors, and render the
//   minimized event timeline with AI-native exposure labels. Renders only minimized event
//   metadata — never pasted text, prompts, or AI responses. Dependencies: api, permissions, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { BrowserSensorApiError, browserSensorApi } from '@/services/browserSensorApi';
import type {
  BrowserEvent,
  DestinationClass,
  DomainRule,
  PolicyDoc,
  SensorSummary,
} from '@/services/browserSensorTypes';
import {
  availableActions,
  classificationTone,
  exposureLabel,
  isStale,
  statusTone,
} from '@/services/browserSensorPermissions';

const CLASSES: DestinationClass[] = ['approved', 'conditional', 'shadow', 'ignored'];

export function BrowserSensorPanel({ scopes }: { scopes: readonly string[] }) {
  const [sensors, setSensors] = useState<SensorSummary[] | null>(null);
  const [policy, setPolicy] = useState<PolicyDoc | null>(null);
  const [events, setEvents] = useState<BrowserEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [rules, setRules] = useState<DomainRule[]>([]);
  const [enabled, setEnabled] = useState(false);

  const canManageSensors = scopes.includes('browser_sensors:manage');
  const canManagePolicy = scopes.includes('browser_policy:manage');
  const canReadEvents = scopes.includes('browser_events:read');

  const refresh = useCallback(async () => {
    try {
      setSensors(await browserSensorApi.sensors());
      const p = await browserSensorApi.policy().catch(() => null);
      setPolicy(p);
      if (p) {
        setRules(p.rules);
        setEnabled(p.enabled);
      }
      if (canReadEvents) setEvents(await browserSensorApi.events().catch(() => []));
      setError(null);
    } catch (err) {
      setError(err instanceof BrowserSensorApiError ? err.message : 'Failed to load.');
    }
  }, [canReadEvents]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createToken = useCallback(async () => {
    setBusy('token');
    try {
      setToken((await browserSensorApi.createEnrollmentToken()).token);
      setError(null);
    } catch (err) {
      setError(err instanceof BrowserSensorApiError ? err.message : 'Failed to create token.');
    } finally {
      setBusy(null);
    }
  }, []);

  const act = useCallback(
    async (id: string, action: 'revoke' | 'rotate') => {
      if (action === 'revoke' && !window.confirm('Revoke this sensor? It can no longer report.')) {
        return;
      }
      setBusy(`${id}:${action}`);
      try {
        if (action === 'rotate') {
          const res = await browserSensorApi.rotate(id);
          window.alert(`New signing secret (shown once):\n${res.signing_secret}`);
        } else {
          await browserSensorApi.revoke(id);
        }
        await refresh();
        setError(null);
      } catch (err) {
        setError(err instanceof BrowserSensorApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const savePolicy = useCallback(async () => {
    setBusy('policy');
    try {
      const saved = await browserSensorApi.updatePolicy({
        enabled,
        trace_match_mode: policy?.trace_match_mode ?? 'exact',
        local_only_mode: policy?.local_only_mode ?? false,
        event_reporting_enabled: policy?.event_reporting_enabled ?? true,
        show_user_notification: policy?.show_user_notification ?? true,
        allow_pause: policy?.allow_pause ?? true,
        min_extension_version: policy?.min_extension_version ?? '0.1.0',
        rules: rules.filter((r) => r.domain.trim().length > 0),
      });
      setPolicy(saved);
      setError(null);
    } catch (err) {
      setError(err instanceof BrowserSensorApiError ? err.message : 'Failed to save policy.');
    } finally {
      setBusy(null);
    }
  }, [enabled, policy, rules]);

  if (sensors === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading browser sensors…</Card>;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Browser sensors (AI paste)</h2>
        <div className="flex gap-2">
          {canManageSensors && (
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
          <p className="text-xs text-muted-foreground">
            Enter this in the extension popup. It expires shortly and can be used once.
          </p>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        Sensors report only a matched trace id and destination classification. Pasted text, prompts,
        and AI responses are never captured or stored.
      </p>

      {sensors?.length === 0 && (
        <Card className="p-4 text-sm text-muted-foreground">No sensors enrolled yet.</Card>
      )}
      {sensors?.map((s) => {
        const actions = availableActions(s.status, scopes);
        return (
          <Card key={s.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
            <Badge tone={statusTone(s.status)}>{s.status}</Badge>
            {isStale(s) && <Badge tone="warning">stale</Badge>}
            <span className="font-mono">{s.sensor_public_id}</span>
            <span className="text-muted-foreground">
              {s.name} · {s.browser_family} · v{s.extension_version}
            </span>
            <span className="text-xs text-muted-foreground">
              {s.last_seen_at ? `seen ${s.last_seen_at.slice(0, 19)}` : 'never seen'}
            </span>
            <span className="ml-auto flex gap-2">
              {actions.map((a) => (
                <Button
                  key={a}
                  variant={a === 'revoke' ? 'primary' : 'secondary'}
                  disabled={busy !== null}
                  onClick={() => void act(s.id, a)}
                >
                  {busy === `${s.id}:${a}` ? '…' : a === 'revoke' ? 'Revoke' : 'Rotate'}
                </Button>
              ))}
            </span>
          </Card>
        );
      })}

      {canManagePolicy && (
        <Card className="space-y-2 p-4 text-sm">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">AI policy (approved / shadow domains)</h3>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              enabled
            </label>
          </div>
          {rules.map((rule, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className="flex-1 rounded border px-2 py-1 font-mono text-xs"
                placeholder="ai-tool.example.com"
                value={rule.domain}
                onChange={(e) =>
                  setRules(rules.map((r, j) => (j === i ? { ...r, domain: e.target.value } : r)))
                }
              />
              <select
                className="rounded border px-2 py-1 text-xs"
                value={rule.classification}
                onChange={(e) =>
                  setRules(
                    rules.map((r, j) =>
                      j === i ? { ...r, classification: e.target.value as DestinationClass } : r,
                    ),
                  )
                }
              >
                {CLASSES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <Button variant="secondary" onClick={() => setRules(rules.filter((_, j) => j !== i))}>
                Remove
              </Button>
            </div>
          ))}
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => setRules([...rules, { domain: '', classification: 'shadow' }])}
            >
              Add domain
            </Button>
            <Button disabled={busy !== null} onClick={() => void savePolicy()}>
              {busy === 'policy' ? '…' : `Save policy${policy ? ` (v${policy.policy_version})` : ''}`}
            </Button>
          </div>
        </Card>
      )}

      {canReadEvents && (
        <Card className="space-y-2 p-4 text-sm">
          <h3 className="font-semibold">Recent AI paste events</h3>
          <p className="text-xs text-muted-foreground">
            Deterministic evidence only. No pasted text, prompts, or model output is stored.
          </p>
          {events?.length === 0 && <p className="text-muted-foreground">No events yet.</p>}
          {events?.map((e) => (
            <div key={e.id} className="flex flex-wrap items-center gap-2 border-t pt-1 text-xs">
              <Badge tone={classificationTone(e.destination_classification)}>
                {e.destination_classification}
              </Badge>
              <Badge tone="warning">{exposureLabel(e)}</Badge>
              <span className="font-mono">{e.trace_id}</span>
              <span className="text-muted-foreground">
                → {e.destination_domain} · {e.observed_at.slice(0, 19)} · {e.match_method}
              </span>
              <span className="font-mono text-muted-foreground">{e.minimized_metadata}</span>
            </div>
          ))}
        </Card>
      )}
    </section>
  );
}
