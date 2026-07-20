// Purpose: Coverage page — risk-weighted measured coverage, confidence, covered/unknown breakdown,
//   surface matrix, blind spots, and ranked placement recommendations.
// Responsibilities: render the latest immutable snapshot with honest measured/inferred/unknown
//   labels (never a bare misleading 100%), the surface risk-vs-coverage table, blind-spot list,
//   ranked recommendations with expected gain/effort/risk and accept/dismiss, a trend delta, the
//   methodology version + last-calculation time, and a manual recalculate. Dependencies: api,
//   permissions, ui.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CoverageApiError, coverageApi } from '@/services/coverageApi';
import type {
  CoverageGap,
  CoverageRecommendation,
  CoverageSnapshot,
  CoverageStatus,
  CoverageSurface,
} from '@/services/coverageTypes';
import {
  confidenceLabel,
  isMisleading,
  scorePercent,
  scoreTone,
  severityTone,
  surfaceTone,
  trendDelta,
  unknownPercent,
} from '@/services/coveragePermissions';

export function CoveragePanel({ scopes }: { scopes: readonly string[] }) {
  const [status, setStatus] = useState<CoverageStatus | null>(null);
  const [snapshots, setSnapshots] = useState<CoverageSnapshot[]>([]);
  const [surfaces, setSurfaces] = useState<CoverageSurface[]>([]);
  const [gaps, setGaps] = useState<CoverageGap[]>([]);
  const [recs, setRecs] = useState<CoverageRecommendation[]>([]);
  const [methodology, setMethodology] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const canRecalc = scopes.includes('coverage:recalculate') || scopes.includes('coverage:manage_policy');
  const canManage = scopes.includes('coverage:manage_policy');

  const refresh = useCallback(async () => {
    try {
      const s = await coverageApi.status();
      setStatus(s);
      setMethodology((await coverageApi.methodology()).methodology_version);
      if (s.status === 'ok') {
        setSnapshots(await coverageApi.snapshots().catch(() => []));
        setSurfaces(await coverageApi.surfaces().catch(() => []));
        setGaps(await coverageApi.gaps().catch(() => []));
        setRecs(await coverageApi.recommendations().catch(() => []));
      }
      setError(null);
    } catch (err) {
      setError(err instanceof CoverageApiError ? err.message : 'Failed to load.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const recalc = useCallback(async () => {
    setBusy('recalc');
    try {
      await coverageApi.recalculate();
      await refresh();
    } catch (err) {
      setError(err instanceof CoverageApiError ? err.message : 'Recalculation failed.');
    } finally {
      setBusy(null);
    }
  }, [refresh]);

  const actOnRec = useCallback(
    async (id: string, action: 'accept' | 'dismiss') => {
      setBusy(`${id}:${action}`);
      try {
        if (action === 'accept') await coverageApi.acceptRecommendation(id);
        else await coverageApi.dismissRecommendation(id);
        await refresh();
      } catch (err) {
        setError(err instanceof CoverageApiError ? err.message : 'Action failed.');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  if (status === null && error === null) {
    return <Card className="p-4 text-sm text-muted-foreground">Loading coverage…</Card>;
  }

  const snapshot = status?.snapshot;
  const delta = trendDelta(snapshots);

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Deception coverage (measured)</h2>
        {canRecalc && (
          <Button onClick={() => void recalc()} disabled={busy !== null}>
            {busy === 'recalc' ? '…' : 'Recalculate'}
          </Button>
        )}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {status?.status === 'no_snapshot' && (
        <Card className="p-4 text-sm text-muted-foreground">
          No coverage snapshot yet. Coverage is measured from real active controls — it is not
          estimated. Run a calculation to measure your current coverage.
        </Card>
      )}

      {snapshot && (
        <>
          <Card className="space-y-2 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-3xl font-semibold">{scorePercent(snapshot.overall_score)}</span>
              <Badge tone={scoreTone(snapshot.overall_score)}>risk-weighted coverage</Badge>
              <Badge tone="info">{confidenceLabel(snapshot.confidence)}</Badge>
              <span className="text-xs text-muted-foreground">
                confidence {Math.round(snapshot.confidence * 100)}% · unknown{' '}
                {unknownPercent(snapshot)} · methodology {methodology}
              </span>
            </div>
            {isMisleading(snapshot) && (
              <p className="text-sm text-amber-600">
                ⚠ This score is qualified: significant unknown inventory or low confidence means it
                is not measured certainty.
              </p>
            )}
            <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
              <span>active decoys: {snapshot.active_decoys}</span>
              <span>active sensors: {snapshot.active_sensors}</span>
              <span className={snapshot.unhealthy_sensors ? 'text-amber-600' : ''}>
                unhealthy sensors: {snapshot.unhealthy_sensors}
              </span>
              <span className={snapshot.expired_decoys ? 'text-amber-600' : ''}>
                expired decoys: {snapshot.expired_decoys}
              </span>
              <span>blind spots: {snapshot.blind_spot_count}</span>
              {delta !== null && (
                <span className={delta >= 0 ? 'text-emerald-600' : 'text-red-600'}>
                  trend {delta >= 0 ? '+' : ''}
                  {Math.round(delta * 100)}%
                </span>
              )}
              <span>calculated {snapshot.calculated_at.slice(0, 19)}</span>
            </div>
          </Card>

          {surfaces.length > 0 && (
            <Card className="space-y-1 p-4 text-xs">
              <p className="text-sm font-semibold">Surfaces (risk vs coverage)</p>
              {surfaces.map((s) => (
                <div key={`${s.surface_type}:${s.external_or_resource_id}`}
                  className="flex flex-wrap items-center gap-2 border-t pt-1">
                  <Badge tone={surfaceTone(s)}>{s.surface_type}</Badge>
                  {s.status === 'unknown' && <Badge tone="info">unknown</Badge>}
                  <span className="font-mono">{s.display_name}</span>
                  <span className="text-muted-foreground">
                    risk {s.risk_weight.toFixed(2)} · coverage {scorePercent(s.surface_coverage)} ·{' '}
                    conf {Math.round(s.confidence * 100)}%
                  </span>
                </div>
              ))}
            </Card>
          )}

          {gaps.length > 0 && (
            <Card className="space-y-1 p-4 text-xs">
              <p className="text-sm font-semibold">Critical blind spots</p>
              {gaps.map((g, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 border-t pt-1">
                  <Badge tone={severityTone(g.severity)}>{g.severity}</Badge>
                  <span className="font-mono">{g.gap_type.replace(/_/g, ' ')}</span>
                  <span className="text-muted-foreground">
                    {g.external_or_resource_id}: {g.reason} (+
                    {Math.round(g.expected_coverage_gain * 100)}%)
                  </span>
                </div>
              ))}
            </Card>
          )}

          {recs.length > 0 && (
            <Card className="space-y-1 p-4 text-xs">
              <p className="text-sm font-semibold">Top recommended placements</p>
              {recs.map((r) => (
                <div key={r.id} className="flex flex-wrap items-center gap-2 border-t pt-1">
                  <Badge tone="info">priority {r.priority_score.toFixed(2)}</Badge>
                  <span className="font-mono">{r.recommended_action.replace(/_/g, ' ')}</span>
                  <span className="text-muted-foreground">
                    {r.target_location}: +{Math.round(r.expected_coverage_gain * 100)}% coverage,
                    risk {r.deployment_risk.toFixed(2)}, effort {r.implementation_effort.toFixed(2)}
                  </span>
                  {canManage && r.status === 'open' && (
                    <span className="ml-auto flex gap-1">
                      <Button
                        disabled={busy !== null}
                        onClick={() => void actOnRec(r.id, 'accept')}
                      >
                        {busy === `${r.id}:accept` ? '…' : 'Accept'}
                      </Button>
                      <Button
                        variant="secondary"
                        disabled={busy !== null}
                        onClick={() => void actOnRec(r.id, 'dismiss')}
                      >
                        Dismiss
                      </Button>
                    </span>
                  )}
                  {r.status !== 'open' && <Badge tone="info">{r.status}</Badge>}
                </div>
              ))}
              <p className="pt-1 text-muted-foreground">
                Accepting a recommendation records intent only — it never deploys automatically; the
                normal approval flow still applies.
              </p>
            </Card>
          )}
        </>
      )}
    </section>
  );
}
