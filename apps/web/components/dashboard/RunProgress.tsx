// Purpose: render the one-click demo run's step progress and coverage.
// Responsibilities: show each pipeline step's status, the weighted coverage bars, and a Markdown
//   export link. Dependencies: Card, Badge, the API export URL, and the demo run types.
import { CheckCircle2, CircleDashed, Loader2, XCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/services/api';
import { DemoRunStepStatus, type CoverageSummary, type DemoRun } from '@/services/types';

const STATUS_ICON = {
  [DemoRunStepStatus.Pending]: <CircleDashed className="h-4 w-4 text-slate-600" />,
  [DemoRunStepStatus.Running]: <Loader2 className="h-4 w-4 animate-spin text-sky-400" />,
  [DemoRunStepStatus.Complete]: <CheckCircle2 className="h-4 w-4 text-emerald-400" />,
  [DemoRunStepStatus.Failed]: <XCircle className="h-4 w-4 text-red-400" />,
};

const COVERAGE_DIMENSIONS: readonly (readonly [keyof CoverageSummary, string])[] = [
  ['repository', 'Repository'],
  ['placement', 'Placement'],
  ['decoy_activation', 'Decoy activation'],
  ['monitoring', 'Monitoring'],
  ['alerting', 'Alerting'],
  ['incident', 'Incident'],
  ['ai_narrative', 'AI narrative'],
];

function CoverageBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span>{Math.round(value * 100)}%</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-slate-800">
        <div
          className="h-2 rounded-full bg-sky-500"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function RunProgress({ run }: { run: DemoRun }) {
  const failed = run.status === 'failed';
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          Demo run
          <Badge tone={failed ? 'danger' : 'success'}>{run.status}</Badge>
        </CardTitle>
        <a
          href={api.exportRunUrl(run.run_id)}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-sky-400 hover:underline"
        >
          Export Markdown
        </a>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        <ol className="space-y-2">
          {run.steps.map((step) => (
            <li key={step.key} className="flex items-center gap-2 text-sm">
              {STATUS_ICON[step.status]}
              <span className="text-slate-200">{step.label}</span>
              {step.note ? <span className="text-xs text-slate-500">· {step.note}</span> : null}
            </li>
          ))}
        </ol>

        <div>
          <div className="mb-3 flex items-baseline justify-between">
            <p className="text-xs uppercase tracking-wide text-slate-500">Deception coverage</p>
            <p className="text-2xl font-semibold text-sky-400">
              {Math.round(run.coverage.overall * 100)}%
            </p>
          </div>
          <div className="space-y-2">
            {COVERAGE_DIMENSIONS.map(([key, label]) => (
              <CoverageBar key={key} label={label} value={run.coverage[key]} />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
