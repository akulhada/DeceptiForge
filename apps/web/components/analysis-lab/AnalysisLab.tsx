// Purpose: the Interactive Demo Lab — authenticated, organization-scoped product experience to
//   enter structured repository signals, run DeceptiForge's deterministic analysis, inspect the
//   reasoning, compare scenarios, and export. No filesystem scan, no repo clone, no GPT.
// Responsibilities: JSON editing (no eval, no raw HTML render), scenario selection, run/reset,
//   stale-result tracking, explainable result sections, comparison, and JSON/Markdown export.
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { getSession } from '@/services/authSession';
import { AnalysisApiError, listScenarios, runPreview } from '@/services/analysisLabApi';
import type {
  AnalysisPreviewResponse,
  ConfidenceBreakdown,
  ScenarioSummary,
} from '@/services/analysisLabTypes';
import { safeFilename, toJson, toMarkdown } from '@/services/analysisLabExport';

interface ParsePosition {
  line: number;
  column: number;
}

function locateError(text: string, error: unknown): ParsePosition | null {
  const message = error instanceof Error ? error.message : '';
  const match = /position (\d+)/.exec(message);
  if (!match) return null;
  const pos = Number.parseInt(match[1], 10);
  const before = text.slice(0, pos);
  const line = before.split('\n').length;
  const column = pos - before.lastIndexOf('\n');
  return { line, column };
}

function confidenceLabel(value: number): string {
  if (value >= 0.7) return 'High';
  if (value >= 0.4) return 'Moderate';
  return 'Low';
}

function Meter({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  // Confidence is communicated by number + text label, never by color alone.
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-40 shrink-0 text-slate-300">{label}</span>
      <span
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${pct} percent, ${confidenceLabel(value)}`}
        className="h-2 w-32 overflow-hidden rounded bg-slate-700"
      >
        <span className="block h-full bg-sky-400" style={{ width: `${pct}%` }} />
      </span>
      <span className="tabular-nums text-slate-200">
        {pct}% · {confidenceLabel(value)}
      </span>
    </div>
  );
}

const EMPTY_SIGNALS = '{\n  "languages": [],\n  "services": []\n}';

export function AnalysisLab() {
  // Resolve the session after mount so SSR and first client render agree (no hydration mismatch).
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    setConnected(getSession() !== null);
  }, []);

  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [scenarioId, setScenarioId] = useState<string>('');
  const [editor, setEditor] = useState<string>(EMPTY_SIGNALS);
  const [parseError, setParseError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisPreviewResponse | null>(null);
  const [stale, setStale] = useState(false);
  const [schemaMismatch, setSchemaMismatch] = useState(false);
  const [running, setRunning] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  const [compareId, setCompareId] = useState<string>('');
  const [compareResult, setCompareResult] = useState<AnalysisPreviewResponse | null>(null);

  const errorRef = useRef<HTMLDivElement | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!connected) return;
    listScenarios()
      .then((list) => {
        setScenarios(list);
        if (list.length > 0) setScenarioId(list[0].id);
      })
      .catch((e) => setApiError(e instanceof Error ? e.message : 'Failed to load scenarios.'));
  }, [connected]);

  const scenarioName = useMemo(
    () => scenarios.find((s) => s.id === scenarioId)?.name ?? null,
    [scenarios, scenarioId],
  );

  const loadSample = useCallback(() => {
    const scenario = scenarios.find((s) => s.id === scenarioId);
    if (!scenario) return;
    setEditor(JSON.stringify(scenario.signals, null, 2));
    setParseError(null);
    setStale(result !== null); // prior result now describes different input
  }, [scenarios, scenarioId, result]);

  const formatJson = useCallback(() => {
    try {
      setEditor(JSON.stringify(JSON.parse(editor), null, 2));
      setParseError(null);
    } catch (e) {
      const pos = locateError(editor, e);
      setParseError(pos ? `Invalid JSON at line ${pos.line}, column ${pos.column}.` : 'Invalid JSON.');
    }
  }, [editor]);

  const onEdit = useCallback(
    (value: string) => {
      setEditor(value);
      if (result) setStale(true);
    },
    [result],
  );

  const run = useCallback(async () => {
    let signals: Record<string, unknown>;
    try {
      signals = JSON.parse(editor) as Record<string, unknown>;
    } catch (e) {
      const pos = locateError(editor, e);
      const msg = pos ? `Invalid JSON at line ${pos.line}, column ${pos.column}.` : 'Invalid JSON.';
      setParseError(msg);
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    setParseError(null);
    setRunning(true);
    setApiError(null);
    try {
      const { response, schemaMismatch: mismatch } = await runPreview(signals, { scenarioId });
      setResult(response);
      setSchemaMismatch(mismatch);
      setStale(false);
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (e) {
      const msg = e instanceof AnalysisApiError ? e.message : 'Analysis failed.';
      setApiError(msg);
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setRunning(false);
    }
  }, [editor, scenarioId]);

  const reset = useCallback(() => {
    setEditor(EMPTY_SIGNALS);
    setParseError(null);
    setResult(null);
    setSchemaMismatch(false);
    setStale(false);
    setApiError(null);
    setCompareResult(null);
    setCompareId('');
    setShowRaw(false);
  }, []);

  const runComparison = useCallback(async () => {
    const scenario = scenarios.find((s) => s.id === compareId);
    if (!scenario) return;
    try {
      const { response } = await runPreview(scenario.signals, { scenarioId: scenario.id });
      setCompareResult(response);
    } catch (e) {
      setApiError(e instanceof AnalysisApiError ? e.message : 'Comparison failed.');
    }
  }, [scenarios, compareId]);

  const download = useCallback(
    (kind: 'json' | 'markdown') => {
      if (!result) return;
      const content = kind === 'json' ? toJson(result) : toMarkdown(result, scenarioName);
      const name = safeFilename(scenarioName, result.schema_version, new Date());
      const blob = new Blob([content], {
        type: kind === 'json' ? 'application/json' : 'text/markdown',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${name}.${kind === 'json' ? 'json' : 'md'}`;
      a.click();
      URL.revokeObjectURL(url);
    },
    [result, scenarioName],
  );

  if (!connected) {
    return (
      <main className="mx-auto max-w-2xl p-8 text-slate-200">
        <h1 className="text-2xl font-semibold">Interactive Analysis Lab</h1>
        <p className="mt-4 text-slate-400">
          Connect a tenant session on the dashboard to use the lab. Analysis is authenticated and
          organization-scoped.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-6 text-slate-200">
      <h1 className="text-2xl font-semibold">Interactive Analysis Lab</h1>
      <p className="mt-1 text-sm text-slate-400">
        Provide structured repository signals and run DeceptiForge&apos;s deterministic analysis.
        Path-like values are descriptive only — nothing is scanned, cloned, executed, or sent to a
        model.
      </p>

      <div
        ref={errorRef}
        tabIndex={-1}
        aria-live="assertive"
        className="mt-4 empty:hidden"
      >
        {parseError && <p className="rounded bg-red-950 p-2 text-sm text-red-200">{parseError}</p>}
        {apiError && <p className="rounded bg-red-950 p-2 text-sm text-red-200">{apiError}</p>}
      </div>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <label htmlFor="scenario" className="block text-sm font-medium text-slate-300">
            Scenario
          </label>
          <div className="mt-1 flex flex-wrap gap-2">
            <select
              id="scenario"
              value={scenarioId}
              onChange={(e) => setScenarioId(e.target.value)}
              className="rounded border border-slate-600 bg-slate-800 p-2 text-sm"
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <Button type="button" onClick={loadSample}>
              Load sample
            </Button>
            <Button type="button" onClick={run} disabled={running}>
              {running ? 'Running…' : 'Run analysis'}
            </Button>
            <Button type="button" variant="secondary" onClick={reset}>
              Reset
            </Button>
          </div>

          <label htmlFor="signals-editor" className="mt-4 block text-sm font-medium text-slate-300">
            Repository signals (JSON)
          </label>
          <textarea
            id="signals-editor"
            value={editor}
            onChange={(e) => onEdit(e.target.value)}
            spellCheck={false}
            aria-describedby="editor-hint"
            className="mt-1 h-80 w-full rounded border border-slate-600 bg-slate-900 p-3 font-mono text-xs"
          />
          <div className="mt-1 flex items-center justify-between">
            <span id="editor-hint" className="text-xs text-slate-500">
              Edited input is not analyzed until you run it.
            </span>
            <button
              type="button"
              onClick={formatJson}
              className="text-xs text-sky-400 underline"
            >
              Format JSON
            </button>
          </div>
        </div>

        <div ref={resultRef} tabIndex={-1} aria-live="polite">
          {stale && (
            <p className="mb-2 rounded bg-amber-950 p-2 text-sm text-amber-200">
              Input changed since the last run — results below are stale. Run analysis again.
            </p>
          )}
          {schemaMismatch && (
            <p className="mb-2 rounded bg-amber-950 p-2 text-sm text-amber-200">
              Result schema version differs from this client. Interpret with caution.
            </p>
          )}
          {result ? (
            <Results result={result} showRaw={showRaw} onToggleRaw={() => setShowRaw((v) => !v)} />
          ) : (
            <p className="text-sm text-slate-500">Run an analysis to see the explained result.</p>
          )}
        </div>
      </section>

      {result && (
        <section className="mt-8 border-t border-slate-700 pt-6">
          <h2 className="text-lg font-semibold">Compare with another scenario</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <label htmlFor="compare" className="text-sm text-slate-300">
              Compare against
            </label>
            <select
              id="compare"
              value={compareId}
              onChange={(e) => setCompareId(e.target.value)}
              className="rounded border border-slate-600 bg-slate-800 p-2 text-sm"
            >
              <option value="">Select scenario…</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <Button type="button" onClick={runComparison} disabled={!compareId}>
              Run comparison
            </Button>
          </div>
          {compareResult && <Comparison left={result} right={compareResult} />}
        </section>
      )}

      {result && (
        <section className="mt-8 flex gap-2 border-t border-slate-700 pt-6">
          <Button type="button" onClick={() => download('json')}>
            Export JSON
          </Button>
          <Button type="button" onClick={() => download('markdown')}>
            Export Markdown
          </Button>
        </section>
      )}
    </main>
  );
}

function Field({ label, value, confidence, reason }: { label: string; value: string; confidence: number; reason: string }) {
  return (
    <li className="rounded border border-slate-700 p-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium">{label.replace(/_/g, ' ')}</span>
        <span className="tabular-nums text-xs text-slate-400">
          {Math.round(confidence * 100)}% · {confidenceLabel(confidence)}
        </span>
      </div>
      <div className="text-sm text-sky-200">{value}</div>
      {reason && <div className="mt-1 text-xs text-slate-400">Deterministic explanation: {reason}</div>}
    </li>
  );
}

function Results({
  result,
  showRaw,
  onToggleRaw,
}: {
  result: AnalysisPreviewResponse;
  showRaw: boolean;
  onToggleRaw: () => void;
}) {
  const cp = result.context_profile;
  return (
    <div className="space-y-5 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Result</h2>
        <button type="button" onClick={onToggleRaw} className="text-xs text-sky-400 underline">
          {showRaw ? 'Hide raw JSON' : 'Show raw JSON'}
        </button>
      </div>

      {showRaw ? (
        <pre className="max-h-96 overflow-auto rounded bg-slate-950 p-3 text-xs">{toJson(result)}</pre>
      ) : (
        <>
          <section aria-labelledby="h-summary">
            <h3 id="h-summary" className="font-semibold text-slate-100">
              Input summary
            </h3>
            <p className="text-slate-300">
              {result.input_summary.language_count} languages · {result.input_summary.service_count}{' '}
              services · {result.input_summary.database_count} databases ·{' '}
              {result.input_summary.secret_location_count} secrets ·{' '}
              {result.input_summary.ai_surface_count} AI surfaces
            </p>
            {result.input_summary.ignored_fields.length > 0 && (
              <p className="text-xs text-amber-300">
                Ignored fields: {result.input_summary.ignored_fields.join(', ')}
              </p>
            )}
          </section>

          <section aria-labelledby="h-profile">
            <h3 id="h-profile" className="font-semibold text-slate-100">
              Inferred profile
            </h3>
            <ul className="mt-1 space-y-1">
              <Field label={cp.probable_business_domain.key} value={cp.probable_business_domain.value} confidence={cp.probable_business_domain.confidence} reason={cp.probable_business_domain.reason} />
              <Field label={cp.probable_repository_type.key} value={cp.probable_repository_type.value} confidence={cp.probable_repository_type.confidence} reason={cp.probable_repository_type.reason} />
              <Field label={cp.service_architecture.key} value={cp.service_architecture.value} confidence={cp.service_architecture.confidence} reason={cp.service_architecture.reason} />
              <Field label={cp.data_sensitivity.key} value={cp.data_sensitivity.value} confidence={cp.data_sensitivity.confidence} reason={cp.data_sensitivity.reason} />
              <Field label={cp.deployment_model.key} value={cp.deployment_model.value} confidence={cp.deployment_model.confidence} reason={cp.deployment_model.reason} />
              <Field label={cp.ai_system_exposure.key} value={cp.ai_system_exposure.value} confidence={cp.ai_system_exposure.confidence} reason={cp.ai_system_exposure.reason} />
            </ul>
          </section>

          <section aria-labelledby="h-vocab">
            <h3 id="h-vocab" className="font-semibold text-slate-100">
              Vocabulary &amp; naming
            </h3>
            <p className="text-slate-300">
              Domain terms: {result.vocabulary.domain_terms.join(', ') || '—'}
            </p>
            <ul className="list-disc pl-5 text-xs text-slate-400">
              {result.vocabulary.influence_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="h-zones">
            <h3 id="h-zones" className="font-semibold text-slate-100">
              Sensitive zones
            </h3>
            <ul className="mt-1 space-y-1">
              {result.sensitive_zones.map((z) => (
                <li key={z.zone_id} className="rounded border border-slate-700 p-2">
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium">{z.category}</span>
                    <span className="tabular-nums text-xs text-slate-400">
                      risk {Math.round(z.risk_score * 100)}% · conf {Math.round(z.confidence * 100)}%
                    </span>
                  </div>
                  <div className="text-xs text-slate-400">{z.reasoning}</div>
                  {z.warnings.map((w) => (
                    <div key={w} className="text-xs text-amber-300">
                      {w}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="h-place">
            <h3 id="h-place" className="font-semibold text-slate-100">
              Placement recommendations
            </h3>
            <ol className="mt-1 space-y-1">
              {result.placement_recommendations.map((p) => (
                <li key={p.rank} className="rounded border border-slate-700 p-2">
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium">
                      #{p.rank} {p.zone} → <code className="text-sky-200">{p.proposed_path_or_pattern}</code>
                    </span>
                    <span className="tabular-nums text-xs text-slate-400">
                      {p.decoy_type} · conf {Math.round(p.confidence * 100)}%
                    </span>
                  </div>
                  <div className="text-xs text-slate-400">{p.reasoning}</div>
                </li>
              ))}
            </ol>
          </section>

          <section aria-labelledby="h-conf">
            <h3 id="h-conf" className="font-semibold text-slate-100">
              Confidence
            </h3>
            <ConfidenceView c={result.confidence} />
          </section>

          <section aria-labelledby="h-warn">
            <h3 id="h-warn" className="font-semibold text-slate-100">
              Warnings
            </h3>
            {result.warnings.length === 0 ? (
              <p className="text-slate-400">None.</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {result.warnings.map((w) => (
                  <li key={w.code} className="rounded border border-amber-800 p-2 text-xs">
                    <span className="font-medium text-amber-200">{w.code}</span>: {w.message}{' '}
                    <span className="text-slate-400">{w.effect}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p className="text-xs text-slate-500">
            Schema {result.schema_version} · engines{' '}
            {Object.entries(result.engine_versions)
              .map(([k, v]) => `${k} ${v}`)
              .join(', ')}{' '}
            · request {result.request_id}
          </p>
        </>
      )}
    </div>
  );
}

function ConfidenceView({ c }: { c: ConfidenceBreakdown }) {
  return (
    <div className="mt-1 space-y-1">
      <Meter label="Overall" value={c.overall} />
      <Meter label="Domain" value={c.domain} />
      <Meter label="Vocabulary" value={c.vocabulary} />
      <Meter label="Sensitive zones" value={c.sensitive_zone} />
      <Meter label="Placement" value={c.placement} />
      <Meter label="Completeness" value={c.completeness} />
      <Meter label="Conflict" value={c.conflict} />
    </div>
  );
}

function Comparison({ left, right }: { left: AnalysisPreviewResponse; right: AnalysisPreviewResponse }) {
  const rows: [string, string, string][] = [
    ['Business domain', left.context_profile.probable_business_domain.value, right.context_profile.probable_business_domain.value],
    ['Architecture', left.context_profile.service_architecture.value, right.context_profile.service_architecture.value],
    ['Data sensitivity', left.context_profile.data_sensitivity.value, right.context_profile.data_sensitivity.value],
    ['AI exposure', left.context_profile.ai_system_exposure.value, right.context_profile.ai_system_exposure.value],
    ['Top zone', left.sensitive_zones[0]?.category ?? '—', right.sensitive_zones[0]?.category ?? '—'],
    ['Overall confidence', `${Math.round(left.confidence.overall * 100)}%`, `${Math.round(right.confidence.overall * 100)}%`],
    ['Conflict', `${Math.round(left.confidence.conflict * 100)}%`, `${Math.round(right.confidence.conflict * 100)}%`],
    ['Warnings', String(left.warnings.length), String(right.warnings.length)],
  ];
  const schemaDiffers = left.schema_version !== right.schema_version;
  return (
    <div className="mt-3 overflow-x-auto">
      {schemaDiffers && (
        <p className="mb-2 rounded bg-amber-950 p-2 text-xs text-amber-200">
          Schema versions differ; comparison may be unreliable.
        </p>
      )}
      <table className="w-full text-sm">
        <caption className="sr-only">Side-by-side scenario comparison</caption>
        <thead>
          <tr className="text-left text-slate-400">
            <th scope="col" className="p-1">Dimension</th>
            <th scope="col" className="p-1">Current</th>
            <th scope="col" className="p-1">Comparison</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([dim, a, b]) => (
            <tr key={dim} className={a !== b ? 'bg-slate-800' : ''}>
              <th scope="row" className="p-1 font-normal text-slate-300">
                {dim}
              </th>
              <td className="p-1 tabular-nums">{a}</td>
              <td className="p-1 tabular-nums">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
