// Purpose: pure presentation helpers for the coverage view — score/confidence labels, honesty
//   guards (never show a bare 100%), surface/gap tones, and trend deltas. No network or DOM.
import type { CoverageSnapshot, CoverageSurface } from './coverageTypes';

// Format a 0..1 score as a percent string. Never rounds 0.99something up to a misleading "100%"
// unless it is genuinely 1.0.
export function scorePercent(score: number): string {
  if (score >= 1) return '100%';
  return `${Math.floor(score * 100)}%`;
}

// A high score with low confidence must be shown as qualified, never as measured certainty.
export function confidenceLabel(confidence: number): 'measured' | 'inferred' | 'low-confidence' {
  if (confidence >= 0.75) return 'measured';
  if (confidence >= 0.5) return 'inferred';
  return 'low-confidence';
}

export function isMisleading(snapshot: CoverageSnapshot): boolean {
  // A near-perfect score with meaningful unknown weight or low confidence is misleading.
  const unknownRatio =
    snapshot.unknown_weight / (snapshot.total_weight + snapshot.unknown_weight || 1);
  return snapshot.overall_score >= 0.99 && (unknownRatio > 0.05 || snapshot.confidence < 0.75);
}

export function scoreTone(score: number): 'info' | 'success' | 'warning' | 'danger' {
  if (score >= 0.8) return 'success';
  if (score >= 0.5) return 'warning';
  return 'danger';
}

export function surfaceTone(surface: CoverageSurface): 'info' | 'success' | 'warning' | 'danger' {
  if (surface.status === 'unknown') return 'info';
  if (surface.surface_coverage >= 0.8) return 'success';
  if (surface.surface_coverage >= 0.5) return 'warning';
  return 'danger';
}

export function severityTone(severity: string): 'info' | 'success' | 'warning' | 'danger' {
  if (severity === 'critical' || severity === 'high') return 'danger';
  if (severity === 'medium') return 'warning';
  return 'info';
}

export function trendDelta(snapshots: CoverageSnapshot[]): number | null {
  if (snapshots.length < 2) return null;
  // snapshots are newest-first.
  return snapshots[0].overall_score - snapshots[1].overall_score;
}

export function unknownPercent(snapshot: CoverageSnapshot): string {
  const total = snapshot.total_weight + snapshot.unknown_weight;
  if (total <= 0) return '0%';
  return `${Math.round((snapshot.unknown_weight / total) * 100)}%`;
}
