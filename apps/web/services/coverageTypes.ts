// Purpose: types for the measured coverage engine admin surface.
// Responsibilities: mirror the backend contracts (snapshot, surfaces, gaps, recommendations,
//   methodology). No behavior.

export interface CoverageSnapshot {
  id: string;
  calculated_at: string;
  overall_score: number;
  confidence: number;
  covered_weight: number;
  total_weight: number;
  unknown_weight: number;
  active_decoys: number;
  active_sensors: number;
  unhealthy_sensors: number;
  expired_decoys: number;
  blind_spot_count: number;
  methodology_version: string;
  source_state_hash: string;
}

export interface CoverageStatus {
  status: 'ok' | 'no_snapshot';
  methodology_version?: string;
  snapshot?: CoverageSnapshot;
}

export interface CoverageSurface {
  surface_type: string;
  external_or_resource_id: string;
  display_name: string;
  criticality: number;
  risk_weight: number;
  surface_coverage: number;
  confidence: number;
  status: string;
}

export interface CoverageGap {
  surface_type: string;
  external_or_resource_id: string;
  gap_type: string;
  severity: string;
  reason: string;
  missing_controls: string;
  expected_coverage_gain: number;
}

export interface CoverageRecommendation {
  id: string;
  surface_type: string;
  external_or_resource_id: string;
  recommended_action: string;
  recommended_decoy_type: string | null;
  target_location: string;
  expected_coverage_gain: number;
  expected_detection_gain: number;
  deployment_risk: number;
  false_positive_risk: number;
  implementation_effort: number;
  priority_score: number;
  confidence: number;
  explanation: string;
  status: string;
}

export interface CoverageMethodology {
  methodology_version: string;
  dimension_weights: Record<string, number>;
  notes: string;
}
