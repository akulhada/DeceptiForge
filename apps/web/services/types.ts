// Purpose: expose the shared demo contract to the dashboard under local names.
// Responsibilities: re-export the single source of truth from @deceptiforge/contracts so component
//   imports stay stable while the shapes and enums live in the shared package (no duplication).
// Dependencies: the workspace contracts package.
export {
  BelievabilityDecision as Decision,
  NarrativeSource,
  NarrativeStatus,
  Severity,
} from '@deceptiforge/contracts';

export type {
  DemoState,
  DemoTechnologyEvidence as TechnologyEvidence,
  DemoNamingProfile as NamingProfile,
  DemoNamingConvention as NamingConvention,
  DemoRiskArea as RiskArea,
  DemoRepositoryProfileSummary as RepositoryProfile,
  DemoContextSummary as ContextProfile,
  DemoPlacementSummary as PlacementRecommendation,
  DemoPlacementPlanSummary as PlacementPlan,
  DemoDecoySummary as DecoyAsset,
  DemoDecoyPlanSummary as DecoyPlan,
  DemoValidationSummary as ValidationReport,
  DemoMonitoringEventSummary as DetectionEvent,
  DemoAlertSummary as Alert,
  DemoTimelineEntry as TimelineEntry,
  DemoIncidentSummary as Incident,
  DemoOverviewSummary as Overview,
  IncidentNarrative,
  IncidentNarrativeBody,
} from '@deceptiforge/contracts';
