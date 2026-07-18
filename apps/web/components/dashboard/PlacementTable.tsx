// Purpose: render ranked placement recommendations.
// Responsibilities: present target, type, priority, confidence, risk, and reasoning. Dependencies:
//   table primitives and types.
import { Badge } from '@/components/ui/badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/table';
import type { PlacementRecommendation } from '@/services/types';

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function PlacementTable({
  recommendations,
}: {
  recommendations: readonly PlacementRecommendation[];
}) {
  return (
    <Table>
      <THead>
        <TR className="border-t-0">
          <TH>Target location</TH>
          <TH>Type</TH>
          <TH>Priority</TH>
          <TH>Confidence</TH>
          <TH>Risk</TH>
          <TH>Reasoning</TH>
        </TR>
      </THead>
      <tbody>
        {recommendations.map((rec) => (
          <TR key={rec.target_location}>
            <TD className="font-mono text-xs text-slate-200">{rec.target_location}</TD>
            <TD>
              <Badge>{rec.target_type}</Badge>
            </TD>
            <TD>{pct(rec.placement_priority)}</TD>
            <TD>{pct(rec.confidence)}</TD>
            <TD>{pct(rec.risk_score)}</TD>
            <TD className="max-w-sm text-xs text-slate-400">{rec.reasoning.join(' ')}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
