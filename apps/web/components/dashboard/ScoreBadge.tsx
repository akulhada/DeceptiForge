// Purpose: render a 0–100 score with a threshold-based tone.
// Responsibilities: turn believability/safety scores into a labeled, colored badge.
import { Badge } from '@/components/ui/badge';

export function ScoreBadge({ label, score }: { label: string; score: number }) {
  const tone = score >= 80 ? 'success' : score >= 60 ? 'warning' : 'danger';
  return (
    <Badge tone={tone}>
      {label} {Math.round(score)}
    </Badge>
  );
}
