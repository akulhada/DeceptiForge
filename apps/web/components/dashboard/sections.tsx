// Purpose: compose the eight dashboard sections from aggregate demo state.
// Responsibilities: map each pipeline artifact to a readable, professional panel with empty states.
// Dependencies: shared dashboard components and UI primitives.
import { AlertTable } from './AlertTable';
import { DecoyCard } from './DecoyCard';
import { EvidenceExcerpt } from './EvidenceExcerpt';
import { IncidentPanel } from './IncidentPanel';
import { MetricCard } from './MetricCard';
import { PlacementTable } from './PlacementTable';
import { DecisionBadge, SeverityBadge } from './SeverityBadge';
import { ScoreBadge } from './ScoreBadge';
import { EmptyState } from './states';
import { Field, Section, TagList } from './primitives';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TD, TH, THead, TR } from '@/components/ui/table';
import type {
  Alert,
  ContextProfile,
  DecoyPlan,
  DetectionEvent,
  Incident,
  Overview,
  PlacementPlan,
  RepositoryProfile,
  TechnologyEvidence,
  ValidationReport,
} from '@/services/types';

const names = (items: TechnologyEvidence[]): string[] => items.map((item) => item.name);
const pct = (value: number): string => `${Math.round(value * 100)}%`;

function CoverageBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-400">
        <span className="capitalize">{label}</span>
        <span>{pct(value)}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-slate-800">
        <div className="h-2 rounded-full bg-sky-500" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  );
}

export function OverviewSection({ overview }: { overview: Overview }) {
  const { coverage } = overview;
  return (
    <Section id="overview" step={0} title="Overview" description="Deception posture at a glance.">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Total decoys" value={overview.total_decoys} />
        <MetricCard label="Accepted" value={overview.accepted_decoys} accent />
        <MetricCard label="Active tripwires" value={overview.active_tripwires} />
        <MetricCard label="Monitor events" value={overview.monitor_events} />
        <MetricCard label="Alerts" value={overview.alerts} />
        <MetricCard label="Incidents" value={overview.incidents} />
      </div>
      <Card className="mt-4 p-4">
        <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">
          Deception coverage (demo estimate)
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <CoverageBar label="repository" value={coverage.repository} />
          <CoverageBar label="database" value={coverage.database} />
          <CoverageBar label="document" value={coverage.document} />
          <CoverageBar label="ai" value={coverage.ai} />
          <CoverageBar label="overall" value={coverage.overall} />
        </div>
      </Card>
    </Section>
  );
}

export function RepositoryProfileSection({
  profile,
  context,
}: {
  profile: RepositoryProfile | null;
  context: ContextProfile | null;
}) {
  return (
    <Section
      id="repository"
      step={1}
      title="Repository Profile"
      description="What the intelligence engine learned about the codebase."
    >
      {profile === null ? (
        <EmptyState title="No repository scanned yet" hint="Seed the demo to scan the sample repository." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{profile.repository_name}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Languages">
                <TagList items={names(profile.languages)} />
              </Field>
              <Field label="Frameworks">
                <TagList items={names(profile.frameworks)} />
              </Field>
              <Field label="Services">
                <TagList items={names(profile.services)} />
              </Field>
              <Field label="Package managers">
                <TagList items={names(profile.package_managers)} />
              </Field>
              <Field label="Databases">
                <TagList items={names(profile.databases)} />
              </Field>
              <Field label="Cloud / CI-CD">
                <TagList items={[...names(profile.cloud_providers), ...names(profile.cicd)]} />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Context & naming</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {context ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Archetype">{context.organization_archetype}</Field>
                  <Field label="Stack maturity">{context.stack_maturity}</Field>
                  <Field label="AI exposure risk">{pct(context.ai_exposure_risk)}</Field>
                  <Field label="DB sensitivity">{pct(context.database_sensitivity_confidence)}</Field>
                </div>
              ) : null}
              <Field label="Environment naming conventions">
                <TagList items={profile.naming_profile ? profile.naming_profile.naming_style.map((n) => `${n.category}:${n.style}`) : []} />
              </Field>
              <Field label="Risk areas">
                {profile.risk_areas.length === 0 ? (
                  <span className="text-xs text-slate-600">None detected</span>
                ) : (
                  <ul className="space-y-1 text-sm">
                    {profile.risk_areas.map((risk, index) => (
                      <li key={index} className="flex items-center gap-2">
                        <SeverityBadge severity={risk.severity} />
                        <span className="text-slate-300">{risk.description}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Field>
            </CardContent>
          </Card>
        </div>
      )}
    </Section>
  );
}

export function PlacementSection({ plan }: { plan: PlacementPlan | null }) {
  return (
    <Section
      id="placements"
      step={2}
      title="Placement Plan"
      description="Where decoys should live, ranked by priority and confidence."
    >
      {plan === null || plan.recommendations.length === 0 ? (
        <EmptyState title="No placement recommendations yet" />
      ) : (
        <Card>
          <CardContent>
            <PlacementTable recommendations={plan.recommendations} />
          </CardContent>
        </Card>
      )}
    </Section>
  );
}

export function DecoySection({ plan }: { plan: DecoyPlan | null }) {
  return (
    <Section
      id="decoys"
      step={3}
      title="Decoy Generation"
      description="Schema-constrained decoys with masked values and trace identifiers."
    >
      {plan === null || plan.assets.length === 0 ? (
        <EmptyState title="No decoys generated yet" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {plan.assets.map((asset) => (
            <DecoyCard key={asset.decoy_id} asset={asset} />
          ))}
        </div>
      )}
    </Section>
  );
}

export function ValidationSection({ reports }: { reports: ValidationReport[] }) {
  return (
    <Section
      id="validation"
      step={4}
      title="Validation Reports"
      description="Believability and safety scoring decides which decoys deploy."
    >
      {reports.length === 0 ? (
        <EmptyState title="No validation reports yet" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {reports.map((report) => (
            <Card key={report.decoy_id}>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle className="font-mono text-xs">{report.decoy_id.slice(0, 8)}</CardTitle>
                <DecisionBadge decision={report.decision} />
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex gap-2">
                  <ScoreBadge label="Believability" score={report.overall_believability_score} />
                  <ScoreBadge label="Safety" score={report.overall_safety_score} />
                </div>
                {report.failed_checks.length > 0 ? (
                  <Field label="Failed checks">
                    <TagList items={report.failed_checks} />
                  </Field>
                ) : null}
                {report.warnings.length > 0 ? (
                  <Field label="Warnings">
                    <span className="text-xs text-amber-300/80">{report.warnings.join(' · ')}</span>
                  </Field>
                ) : null}
                {report.recommended_fixes.length > 0 ? (
                  <Field label="Recommended fixes">
                    <span className="text-xs text-slate-400">
                      {report.recommended_fixes.join(' · ')}
                    </span>
                  </Field>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </Section>
  );
}

export function MonitoringSection({ events }: { events: DetectionEvent[] }) {
  return (
    <Section
      id="monitoring"
      step={5}
      title="Monitoring Events"
      description="Raw tripwire detections with minimized evidence."
    >
      {events.length === 0 ? (
        <EmptyState
          title="No monitor events yet"
          hint="Run “Simulate detection” to trip a decoy."
        />
      ) : (
        <Card>
          <CardContent>
            <Table>
              <THead>
                <TR className="border-t-0">
                  <TH>Trace</TH>
                  <TH>Monitor</TH>
                  <TH>Location</TH>
                  <TH>Time</TH>
                  <TH>Confidence</TH>
                  <TH>Evidence</TH>
                </TR>
              </THead>
              <tbody>
                {events.map((event) => (
                  <TR key={event.event_id}>
                    <TD className="font-mono text-xs text-sky-300">{event.trace_identifier}</TD>
                    <TD>
                      <Badge>{event.monitor_type}</Badge>
                    </TD>
                    <TD className="font-mono text-xs">{event.observed_location}</TD>
                    <TD className="text-xs">{new Date(event.timestamp).toLocaleTimeString()}</TD>
                    <TD>{pct(event.confidence)}</TD>
                    <TD className="min-w-[16rem]">
                      <EvidenceExcerpt
                        excerpt={event.observed_value_excerpt}
                        location={event.observed_location}
                      />
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}
    </Section>
  );
}

export function AlertsSection({ alerts }: { alerts: Alert[] }) {
  return (
    <Section
      id="alerts"
      step={6}
      title="Alerts"
      description="Normalized, deduplicated detections requiring review."
    >
      {alerts.length === 0 ? (
        <EmptyState title="No alerts yet" />
      ) : (
        <Card>
          <CardContent>
            <AlertTable alerts={alerts} />
          </CardContent>
        </Card>
      )}
    </Section>
  );
}

export function IncidentsSection({ incidents }: { incidents: Incident[] }) {
  return (
    <Section
      id="incidents"
      step={7}
      title="Incidents"
      description="Reconstructed timelines with deterministic hypotheses and response actions."
    >
      {incidents.length === 0 ? (
        <EmptyState title="No incidents yet" />
      ) : (
        <div className="space-y-4">
          {incidents.map((incident) => (
            <IncidentPanel key={incident.incident_id} incident={incident} />
          ))}
        </div>
      )}
    </Section>
  );
}
