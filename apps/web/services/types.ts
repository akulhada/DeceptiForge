// Purpose: type the demo API payloads consumed by the dashboard.
// Responsibilities: mirror the serialized backend shapes the UI renders, no more. These are
//   presentation-facing types; the backend Pydantic models remain the validation authority.
// Future modules: replace with the shared contracts package once its shapes match the API.

export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type Decision = 'accept' | 'warn' | 'reject';

export interface TechnologyEvidence {
  name: string;
  confidence: number;
  evidence: string[];
}

export interface NamingConvention {
  category: string;
  style: string;
  separator: string;
  confidence: number;
  samples: string[];
}

export interface NamingProfile {
  naming_style: NamingConvention[];
  common_prefixes: string[];
  common_suffixes: string[];
  confidence: number;
}

export interface RiskArea {
  category: string;
  severity: Severity;
  description: string;
  paths: string[];
}

export interface RepositoryProfile {
  repository_name: string;
  file_count: number;
  is_git_repository: boolean;
  languages: TechnologyEvidence[];
  frameworks: TechnologyEvidence[];
  services: TechnologyEvidence[];
  package_managers: TechnologyEvidence[];
  databases: TechnologyEvidence[];
  cloud_providers: TechnologyEvidence[];
  cicd: TechnologyEvidence[];
  documentation: TechnologyEvidence[];
  mcp_configurations: TechnologyEvidence[];
  infrastructure: {
    docker_files: string[];
    kubernetes_files: string[];
    terraform_files: string[];
  };
  naming_profile: NamingProfile | null;
  secret_locations: { path: string; patterns: string[] }[];
  risk_areas: RiskArea[];
  truncated: boolean;
}

export interface ContextProfile {
  organization_archetype: string;
  stack_maturity: string;
  documentation_culture: string;
  operational_complexity: string;
  ai_exposure_risk: number;
  database_sensitivity_confidence: number;
  environment_naming_conventions: string[];
  likely_sensitive_asset_types: string[];
  confidence: number;
}

export interface PlacementRecommendation {
  target_type: string;
  target_location: string;
  placement_priority: number;
  confidence: number;
  risk_score: number;
  expected_detection_quality: number;
  expected_attacker_agent_visibility: number;
  expected_false_positive_risk: number;
  future_asset_type_recommendation: string;
  reasoning: string[];
}

export interface PlacementPlan {
  recommendations: PlacementRecommendation[];
  rejected_candidates: {
    target_type: string;
    target_location: string;
    rejection_reasons: string[];
  }[];
}

export interface DecoyAsset {
  decoy_id: string;
  decoy_type: string;
  target_location: string;
  target_placement_id: string;
  template_id: string;
  payload: Record<string, unknown>;
  safety_metadata: {
    contains_real_credentials: boolean;
    contains_real_customer_data: boolean;
    safe_for_demo: boolean;
    authentication_capability: string;
  };
  trigger_metadata: { trace_identifier: string; monitoring_status: string };
  validation: { valid: boolean; checks: string[]; reasons: string[] };
  explanation: string[];
}

export interface DecoyPlan {
  repository_name: string;
  assets: DecoyAsset[];
  rejected_candidates: { target_location: string; reasons: string[] }[];
}

export interface ValidationReport {
  decoy_id: string;
  overall_believability_score: number;
  overall_safety_score: number;
  decision: Decision;
  breakdown: Record<string, number>;
  explainability_notes: string[];
  failed_checks: string[];
  warnings: string[];
  recommended_fixes: string[];
}

export interface DetectionEvent {
  event_id: string;
  trace_identifier: string;
  decoy_id: string;
  monitor_type: string;
  observed_location: string;
  observed_value_excerpt: string;
  timestamp: string;
  confidence: number;
  severity_suggestion: Severity;
  detection_method: string;
}

export interface Alert {
  alert_id: string;
  trace_identifier: string;
  decoy_id: string;
  severity: Severity;
  title: string;
  summary: string;
  source_monitor: string;
  confidence: number;
  event_count: number;
  first_seen: string;
  last_seen: string;
  recommended_actions: string[];
}

export interface TimelineEntry {
  sequence: number;
  timestamp: string;
  source: string;
  monitor_type: string;
  summary: string;
  confidence: number;
  evidence: { excerpt: string; digest: string; location: string };
}

export interface Incident {
  incident_id: string;
  title: string;
  severity: Severity;
  incident_type: string;
  confidence: number;
  first_seen: string;
  last_seen: string;
  involved_decoy_ids: string[];
  involved_trace_ids: string[];
  affected_surfaces: string[];
  timeline: TimelineEntry[];
  root_cause_hypothesis: string;
  recommended_actions: string[];
}

export interface Overview {
  total_decoys: number;
  accepted_decoys: number;
  active_tripwires: number;
  monitor_events: number;
  alerts: number;
  incidents: number;
  coverage: {
    repository: number;
    database: number;
    document: number;
    ai: number;
    overall: number;
  };
}

export interface DemoState {
  repository_id: string | null;
  decoy_plan_id: string | null;
  profile: RepositoryProfile | null;
  context: ContextProfile | null;
  placement_plan: PlacementPlan | null;
  decoy_plan: DecoyPlan | null;
  reports: ValidationReport[];
  events: DetectionEvent[];
  alerts: Alert[];
  incidents: Incident[];
  overview: Overview;
}
