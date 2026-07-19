// Purpose: render a unified diff for a deployment change-set item.
// Responsibilities: colorize added/removed/context lines read-only; never execute or fetch. It shows
//   only synthetic, inert decoy content. Dependencies: change-set type.
'use client';

import type { ChangeSetItem } from '@/services/deploymentTypes';

function lineTone(line: string): string {
  if (line.startsWith('+') && !line.startsWith('+++')) return 'text-emerald-600';
  if (line.startsWith('-') && !line.startsWith('---')) return 'text-red-600';
  if (line.startsWith('@@')) return 'text-sky-600';
  return 'text-muted-foreground';
}

export function DeploymentDiff({ item }: { item: ChangeSetItem }) {
  const lines = item.unified_diff.split('\n');
  return (
    <div className="rounded-md border">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2 text-sm">
        <span className="font-mono">{item.target_path}</span>
        <span className="uppercase text-muted-foreground">{item.operation}</span>
      </div>
      <pre className="max-h-80 overflow-auto px-3 py-2 text-xs leading-relaxed">
        {lines.map((line, index) => (
          <div key={index} className={lineTone(line)}>
            {line || ' '}
          </div>
        ))}
      </pre>
      {item.warnings.length > 0 && (
        <ul className="border-t px-3 py-2 text-xs text-amber-600">
          {item.warnings.map((warning) => (
            <li key={warning}>⚠ {warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
