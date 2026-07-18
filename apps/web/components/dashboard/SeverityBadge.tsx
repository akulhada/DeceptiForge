// Purpose: render severity and decision values with consistent security-console colors.
// Responsibilities: map severity/decision vocabularies to badge tones. Dependencies: Badge.
import { Badge } from '@/components/ui/badge';
import type { Decision, Severity } from '@/services/types';

const SEVERITY_TONE: Record<Severity, 'neutral' | 'info' | 'warning' | 'danger'> = {
  info: 'neutral',
  low: 'info',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
};

const DECISION_TONE: Record<Decision, 'success' | 'warning' | 'danger'> = {
  accept: 'success',
  warn: 'warning',
  reject: 'danger',
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge tone={SEVERITY_TONE[severity]} className="uppercase">
      {severity}
    </Badge>
  );
}

export function DecisionBadge({ decision }: { decision: Decision }) {
  return (
    <Badge tone={DECISION_TONE[decision]} className="uppercase">
      {decision}
    </Badge>
  );
}
