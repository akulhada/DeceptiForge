// Purpose: render a reconstructed incident with its timeline and deterministic hypothesis.
// Responsibilities: present severity, type, involved assets, surfaces, hypothesis, actions, and the
//   forensic timeline. Dependencies: Card, Timeline, badges, primitives.
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SeverityBadge } from './SeverityBadge';
import { Timeline } from './Timeline';
import { Field, TagList } from './primitives';
import type { Incident } from '@/services/types';

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
      </CardContent>
    </Card>
  );
}
