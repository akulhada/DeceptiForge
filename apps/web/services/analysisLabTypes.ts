// Purpose: TypeScript mirror of the Interactive Demo Lab contract (analysis-preview-v1).
// Responsibilities: type the preview response and scenario list so the UI stays aligned with the
//   shared Python contract. Keep SCHEMA_VERSION in sync with app/models/domain/analysis_preview.py.

export const SCHEMA_VERSION = 'analysis-preview-v1';

export interface InferredField {
  key: string;
  value: string;
  confidence: number;
  supporting_signals: string[];
  reason: string;
}

export interface ContextProfileView {
  probable_business_domain: InferredField;
  probable_repository_type: InferredField;
  dominant_technical_stack: InferredField;
  service_architecture: InferredField;
  operational_maturity: InferredField;
  data_sensitivity: InferredField;
  deployment_model: InferredField;
  ai_system_exposure: InferredField;
  high_value_attacker_interests: string[];
}

export interface VocabularyView {
  domain_terms: string[];
  entity_names: string[];
  service_names: string[];
  environment_terms: string[];
  operational_vocabulary: string[];
  prefixes: string[];
  suffixes: string[];
  confidence: number;
  supporting_signals: string[];
  influence_notes: string[];
}

export interface SensitiveZone {
  zone_id: string;
  category: string;
  representative_paths: string[];
  risk_score: number;
  confidence: number;
  supporting_signals: string[];
  reasoning: string;
  relevant_decoy_types: string[];
  warnings: string[];
}

export interface PlacementRecommendationView {
  rank: number;
  zone: string;
  proposed_path_or_pattern: string;
  decoy_type: string;
  expected_visibility: number;
  business_relevance: number;
  detection_value: number;
  deployment_risk: number;
  confidence: number;
  supporting_signals: string[];
  reasoning: string;
  lower_ranked_alternatives: string[];
}

export interface InputSummary {
  language_count: number;
  framework_count: number;
  service_count: number;
  database_count: number;
  documentation_signal_count: number;
  secret_location_count: number;
  ai_surface_count: number;
  naming_pattern_count: number;
  recognized_categories: string[];
  ignored_fields: string[];
}

export interface ConfidenceBreakdown {
  overall: number;
  domain: number;
  vocabulary: number;
  sensitive_zone: number;
  placement: number;
  completeness: number;
  conflict: number;
}

export interface AnalysisWarning {
  code: string;
  message: string;
  effect: string;
}

export interface AnalysisPreviewResponse {
  schema_version: string;
  organization_id: string;
  request_id: string;
  scenario_id: string | null;
  input_summary: InputSummary;
  context_profile: ContextProfileView;
  vocabulary: VocabularyView;
  sensitive_zones: SensitiveZone[];
  placement_recommendations: PlacementRecommendationView[];
  warnings: AnalysisWarning[];
  confidence: ConfidenceBreakdown;
  engine_versions: Record<string, string>;
  generated_at: string;
  stage_timings_ms: Record<string, number>;
}

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  signals: Record<string, unknown>;
}

export interface AnalysisOptions {
  include_alternatives?: boolean;
  maximum_recommendations?: number;
  minimum_confidence?: number;
}
