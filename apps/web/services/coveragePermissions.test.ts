// Purpose: verify coverage presentation helpers — honest score formatting, confidence labels,
//   misleading-100% guard, tones, trend delta, unknown percent.
import { describe, expect, it } from 'vitest';

import {
  confidenceLabel,
  isMisleading,
  scorePercent,
  scoreTone,
  severityTone,
  surfaceTone,
  trendDelta,
  unknownPercent,
} from './coveragePermissions';
import type { CoverageSnapshot, CoverageSurface } from './coverageTypes';

function snap(over: Partial<CoverageSnapshot>): CoverageSnapshot {
  return {
    id: 's', calculated_at: '2026-07-19T00:00:00', overall_score: 0.8, confidence: 0.9,
    covered_weight: 8, total_weight: 10, unknown_weight: 0, active_decoys: 2, active_sensors: 2,
    unhealthy_sensors: 0, expired_decoys: 0, blind_spot_count: 1, methodology_version: 'coverage-v1',
    source_state_hash: 'h', ...over,
  };
}

describe('scorePercent', () => {
  it('never rounds up to a misleading 100%', () => {
    expect(scorePercent(0.999)).toBe('99%');
    expect(scorePercent(1)).toBe('100%');
    expect(scorePercent(0.5)).toBe('50%');
  });
});

describe('confidenceLabel', () => {
  it('labels measured vs inferred vs low-confidence', () => {
    expect(confidenceLabel(0.9)).toBe('measured');
    expect(confidenceLabel(0.6)).toBe('inferred');
    expect(confidenceLabel(0.3)).toBe('low-confidence');
  });
});

describe('isMisleading', () => {
  it('flags a near-perfect score with unknown weight or low confidence', () => {
    expect(isMisleading(snap({ overall_score: 1, unknown_weight: 5, total_weight: 5 }))).toBe(true);
    expect(isMisleading(snap({ overall_score: 1, confidence: 0.4 }))).toBe(true);
    expect(isMisleading(snap({ overall_score: 1, unknown_weight: 0, confidence: 0.9 }))).toBe(false);
    expect(isMisleading(snap({ overall_score: 0.7 }))).toBe(false);
  });
});

describe('tones', () => {
  it('maps score/surface/severity', () => {
    expect(scoreTone(0.9)).toBe('success');
    expect(scoreTone(0.6)).toBe('warning');
    expect(scoreTone(0.2)).toBe('danger');
    expect(severityTone('critical')).toBe('danger');
    const surface: CoverageSurface = {
      surface_type: 'repository', external_or_resource_id: 'r', display_name: 'r', criticality: 0.8,
      risk_weight: 0.8, surface_coverage: 0.9, confidence: 0.9, status: 'known',
    };
    expect(surfaceTone(surface)).toBe('success');
    expect(surfaceTone({ ...surface, status: 'unknown' })).toBe('info');
  });
});

describe('trendDelta + unknownPercent', () => {
  it('computes delta from newest-first snapshots', () => {
    expect(trendDelta([])).toBeNull();
    expect(trendDelta([snap({ overall_score: 0.8 }), snap({ overall_score: 0.6 })])).toBeCloseTo(0.2);
  });

  it('computes unknown percent', () => {
    expect(unknownPercent(snap({ total_weight: 8, unknown_weight: 2 }))).toBe('20%');
    expect(unknownPercent(snap({ total_weight: 0, unknown_weight: 0 }))).toBe('0%');
  });
});
