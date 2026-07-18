// Purpose: render a single headline metric for the overview.
// Responsibilities: show a label, value, and optional hint in a compact card. Dependencies: Card.
import type { ReactNode } from 'react';

import { Card } from '@/components/ui/card';

export function MetricCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${accent ? 'text-sky-400' : 'text-slate-100'}`}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </Card>
  );
}
