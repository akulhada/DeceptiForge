// Purpose: verify the DemoState contract compiles with the shared enums and round-trips as JSON.
// Responsibilities: guard against drift by constructing a fully typed sample and serializing it.
import { describe, expect, it } from 'vitest';

import {
  BelievabilityDecision,
  DecoyKind,
  DetectionMethod,
  MonitorType,
  PlacementTargetType,
  Severity,
} from './index';
import type { DemoState } from './index';

const sample: DemoState = {
  repository_id: 'r1',
  decoy_plan_id: 'p1',
  profile: {
    repository_name: 'acme-payments',
    file_count: 10,
    is_git_repository: true,
    languages: [{ name: 'Python', confidence: 0.9, evidence: ['ext'] }],
    frameworks: [],
    services: [],
    package_managers: [],
    databases: [],
    cloud_providers: [],
    cicd: [],
    documentation: [],
    mcp_configurations: [],
    infrastructure: { docker_files: [], kubernetes_files: [], terraform_files: [] },
    naming_profile: null,
    secret_locations: [],
    risk_areas: [],
    truncated: false,
  },
  context: null,
  placement_plan: {
    recommendations: [
      {
        target_type: PlacementTargetType.ExampleEnvironmentFile,
        target_location: '.env.example',
        placement_priority: 0.9,
        confidence: 0.8,
        risk_score: 0.1,
        expected_detection_quality: 0.8,
        expected_attacker_agent_visibility: 0.8,
        expected_false_positive_risk: 0.1,
        future_asset_type_recommendation: DecoyKind.Secret,
        reasoning: ['safe'],
      },
    ],
    rejected_candidates: [],
  },
  decoy_plan: { repository_name: 'acme-payments', assets: [], rejected_candidates: [] },
  reports: [
    {
      decoy_id: 'd1',
      overall_believability_score: 90,
      overall_safety_score: 95,
      decision: BelievabilityDecision.Accept,
      breakdown: { naming_realism: 90 },
      explainability_notes: [],
      failed_checks: [],
      warnings: [],
      recommended_fixes: [],
    },
  ],
  events: [
    {
      event_id: 'e1',
      trace_identifier: 'DFG-A',
      decoy_id: 'd1',
      monitor_type: MonitorType.Repository,
      observed_location: 'src/x.py',
      observed_value_excerpt: 'DFG-A',
      timestamp: '2026-01-01T00:00:00Z',
      confidence: 1,
      severity_suggestion: Severity.High,
      detection_method: DetectionMethod.ContentAccess,
    },
  ],
  alerts: [],
  incidents: [],
  overview: {
    total_decoys: 0,
    accepted_decoys: 0,
    active_tripwires: 0,
    monitor_events: 0,
    alerts: 0,
    incidents: 0,
    coverage: { repository: 0, database: 0, document: 0, ai: 0, overall: 0 },
  },
};

describe('DemoState contract', () => {
  it('serializes and preserves enum-backed fields', () => {
    const parsed = JSON.parse(JSON.stringify(sample)) as DemoState;
    expect(parsed.events[0].severity_suggestion).toBe('high');
    expect(parsed.reports[0].decision).toBe('accept');
    expect(parsed.placement_plan?.recommendations[0].future_asset_type_recommendation).toBe(
      'secret',
    );
  });
});
