// Purpose: render severity and decision values with consistent security-console colors.
// Responsibilities: map the shared Severity/Decision enums to badge tones. Dependencies: Badge.
import { Badge } from '@/components/ui/badge';
import { Decision, Severity } from '@/services/types';

type Tone = 'neutral' | 'info' | 'warning' | 'danger' | 'success';

const SEVERITY_TONE: Record<Severity, Tone> = {
  [Severity.Info]: 'neutral',
  [Severity.Low]: 'info',
  [Severity.Medium]: 'warning',
  [Severity.High]: 'danger',
  [Severity.Critical]: 'danger',
};

const DECISION_TONE: Record<Decision, Tone> = {
  [Decision.Accept]: 'success',
  [Decision.Warn]: 'warning',
  [Decision.Reject]: 'danger',
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
