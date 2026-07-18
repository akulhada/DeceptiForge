// Purpose: render a reconstructed incident plus an optional, on-demand AI investigation summary.
// Responsibilities: present the deterministic incident (source of truth) and let the analyst
//   generate a GPT/fallback narrative from minimized context. Dependencies: Card, Timeline,
//   badges, primitives, Button, and the narrative hook.
'use client';

import { Sparkles } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useIncidentNarrative } from '@/hooks/useIncidentNarrative';
import { SeverityBadge } from './SeverityBadge';
import { Timeline } from './Timeline';
import { Field, TagList } from './primitives';
import type { Incident, IncidentNarrative } from '@/services/types';

function NarrativeList({ title, items }: { title: string; items: readonly string[] }) {
  if (items.length === 0) return null;
  return (
    <Field label={title}>
      <ul className="list-inside list-disc text-sm text-slate-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Field>
  );
}

function NarrativeView({ narrative }: { narrative: IncidentNarrative }) {
  const fallback = narrative.source === 'fallback';
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={fallback ? 'warning' : 'info'}>
          {fallback ? 'Deterministic fallback' : `Model: ${narrative.model ?? 'openai'}`}
        </Badge>
        <span className="text-[11px] text-slate-500">
          Generated from minimized incident context · prompt {narrative.prompt_version}
        </span>
      </div>

      {fallback ? (
        <p className="text-xs text-amber-300/80">
          OpenAI is not configured; this summary was produced deterministically from the incident.
        </p>
      ) : null}

      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Executive summary</p>
        <p className="mt-1 text-sm text-slate-200">{narrative.body.executive_summary}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Analyst summary</p>
        <p className="mt-1 text-sm text-slate-300">{narrative.body.analyst_summary}</p>
      </div>
      <NarrativeList title="Likely sequence" items={narrative.body.likely_sequence} />
      <NarrativeList title="Evidence" items={narrative.body.evidence_summary} />
      <NarrativeList title="Recommended next actions" items={narrative.body.recommended_next_actions} />
      <NarrativeList title="Caveats & uncertainty" items={narrative.body.uncertainty_caveats} />
      {narrative.body.confidence_notes ? (
        <p className="text-xs text-slate-500">{narrative.body.confidence_notes}</p>
      ) : null}
    </div>
  );
}

function AiInvestigationSummary({ incidentId }: { incidentId: string }) {
  const { narrative, loading, error, generate } = useIncidentNarrative(incidentId);

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <Sparkles className="h-4 w-4 text-sky-400" /> AI Investigation Summary
        </p>
        <Button size="sm" variant="secondary" onClick={() => void generate()} disabled={loading}>
          {loading ? 'Generating…' : narrative ? 'Regenerate' : 'Generate AI Summary'}
        </Button>
      </div>

      <div className="mt-3">
        {error ? (
          <p className="text-xs text-red-300">{error}</p>
        ) : loading && narrative === null ? (
          <p className="text-xs text-slate-500">Summarizing minimized incident context…</p>
        ) : narrative ? (
          <NarrativeView narrative={narrative} />
        ) : (
          <p className="text-xs text-slate-500">
            No AI summary yet. Generate one from the minimized incident context on demand.
          </p>
        )}
      </div>
    </div>
  );
}

export function IncidentPanel({ incident }: { incident: Incident }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <SeverityBadge severity={incident.severity} />
          {incident.title}
        </CardTitle>
        <span className="text-xs uppercase text-slate-500">{incident.incident_type}</span>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Affected surfaces">
            <TagList items={incident.affected_surfaces} />
          </Field>
          <Field label="Involved traces">
            <TagList items={incident.involved_trace_ids} />
          </Field>
        </div>

        <div className="rounded-md border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Deterministic hypothesis</p>
          <p className="mt-1 text-sm text-slate-200">{incident.root_cause_hypothesis}</p>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Timeline</p>
          <Timeline entries={incident.timeline} />
        </div>

        <Field label="Response actions">
          <ul className="list-inside list-disc text-sm text-slate-300">
            {incident.recommended_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </Field>

        <AiInvestigationSummary incidentId={incident.incident_id} />
      </CardContent>
    </Card>
  );
}
