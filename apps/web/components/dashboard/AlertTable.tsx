// Purpose: render normalized alerts.
// Responsibilities: present severity, title, source, event count, confidence, and actions.
import { SeverityBadge } from './SeverityBadge';
import { Table, TD, TH, THead, TR } from '@/components/ui/table';
import type { Alert } from '@/services/types';

export function AlertTable({ alerts }: { alerts: readonly Alert[] }) {
  return (
    <Table>
      <THead>
        <TR className="border-t-0">
          <TH>Severity</TH>
          <TH>Title</TH>
          <TH>Source</TH>
          <TH>Events</TH>
          <TH>Confidence</TH>
          <TH>Recommended actions</TH>
        </TR>
      </THead>
      <tbody>
        {alerts.map((alert) => (
          <TR key={alert.alert_id}>
            <TD>
              <SeverityBadge severity={alert.severity} />
            </TD>
            <TD className="text-slate-100">{alert.title}</TD>
            <TD>{alert.source_monitor}</TD>
            <TD>{alert.event_count}</TD>
            <TD>{Math.round(alert.confidence * 100)}%</TD>
            <TD className="max-w-sm text-xs text-slate-400">
              {alert.recommended_actions.join(' · ')}
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
