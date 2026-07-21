// Purpose: verify export produces safe filenames and Markdown/JSON that carry the result contract
//   but no session/auth/secret data.
import { describe, expect, it } from 'vitest';

import { safeFilename, toJson, toMarkdown } from './analysisLabExport';
import type { AnalysisPreviewResponse } from './analysisLabTypes';

const RESPONSE: AnalysisPreviewResponse = {
  schema_version: 'analysis-preview-v1',
  organization_id: 'org-1',
  request_id: 'req-1',
  scenario_id: 'fintech-payments',
  input_summary: {
    language_count: 1, framework_count: 1, service_count: 2, database_count: 1,
    documentation_signal_count: 2, secret_location_count: 1, ai_surface_count: 0,
    naming_pattern_count: 3, recognized_categories: ['services'], ignored_fields: ['bogus'],
  },
  context_profile: {
    probable_business_domain: { key: 'probable_business_domain', value: 'Financial / payments platform', confidence: 0.9, supporting_signals: ['payment'], reason: 'Payment terminology appeared across services.' },
    probable_repository_type: { key: 'probable_repository_type', value: 'microservices', confidence: 0.7, supporting_signals: [], reason: 'r' },
    dominant_technical_stack: { key: 'dominant_technical_stack', value: 'Python', confidence: 0.6, supporting_signals: [], reason: 'r' },
    service_architecture: { key: 'service_architecture', value: 'microservices', confidence: 0.8, supporting_signals: [], reason: 'r' },
    operational_maturity: { key: 'operational_maturity', value: 'mature', confidence: 0.7, supporting_signals: [], reason: 'r' },
    data_sensitivity: { key: 'data_sensitivity', value: 'high', confidence: 0.9, supporting_signals: [], reason: 'r' },
    deployment_model: { key: 'deployment_model', value: 'kubernetes', confidence: 0.7, supporting_signals: [], reason: 'r' },
    ai_system_exposure: { key: 'ai_system_exposure', value: 'none', confidence: 0.1, supporting_signals: [], reason: 'r' },
    high_value_attacker_interests: ['payment'],
  },
  vocabulary: {
    domain_terms: ['payment'], entity_names: [], service_names: ['payment-service'], environment_terms: [],
    operational_vocabulary: [], prefixes: [], suffixes: [], confidence: 0.5, supporting_signals: [],
    influence_notes: ['Domain terms shape decoy terminology.'],
  },
  sensitive_zones: [
    { zone_id: 'zone_payment', category: 'payment', representative_paths: [], risk_score: 0.9, confidence: 0.7, supporting_signals: ['payment'], reasoning: 'Payment evidence matched.', relevant_decoy_types: ['secret'], warnings: [] },
  ],
  placement_recommendations: [
    { rank: 1, zone: 'environment_file', proposed_path_or_pattern: '.env.example', decoy_type: 'secret', expected_visibility: 0.8, business_relevance: 0.7, detection_value: 0.7, deployment_risk: 0.2, confidence: 0.7, supporting_signals: [], reasoning: 'r', lower_ranked_alternatives: [] },
  ],
  warnings: [{ code: 'unknown_fields_ignored', message: 'Ignored unknown fields: bogus.', effect: 'No effect.' }],
  confidence: { overall: 0.7, domain: 0.7, vocabulary: 0.5, sensitive_zone: 0.7, placement: 0.7, completeness: 0.6, conflict: 0 },
  engine_versions: { context_engine: '1.0' },
  generated_at: '2026-07-20T12:00:00Z',
  stage_timings_ms: { mapping: 0.1 },
};

describe('analysisLabExport', () => {
  it('sanitizes filenames', () => {
    const name = safeFilename('Fintech / Payment Platform!!', 'analysis-preview-v1', new Date('2026-07-20T12:00:00Z'));
    expect(name).toMatch(/^fintech-payment-platform_2026-07-20_12-00-00_analysis-preview-v1$/);
    expect(name).not.toContain('/');
    expect(name).not.toContain(' ');
  });

  it('defaults custom filename when no scenario', () => {
    expect(safeFilename(null, 'analysis-preview-v1', new Date())).toContain('custom-analysis');
  });

  it('JSON export is the response contract', () => {
    const parsed = JSON.parse(toJson(RESPONSE));
    expect(parsed.schema_version).toBe('analysis-preview-v1');
    expect(parsed.placement_recommendations).toHaveLength(1);
  });

  it('Markdown export includes all sections and no session/secret data', () => {
    const md = toMarkdown(RESPONSE, 'Fintech');
    for (const section of ['Input summary', 'Inferred profile', 'Vocabulary', 'Sensitive zones', 'Placement recommendations', 'Confidence', 'Warnings']) {
      expect(md).toContain(section);
    }
    expect(md).toContain('analysis-preview-v1');
    expect(md).toContain('Payment evidence matched.');
    // No secrets/session/auth material.
    expect(md).not.toContain('dfk_');
    expect(md).not.toContain('X-DeceptiForge-API-Key');
    expect(md.toLowerCase()).not.toContain('apikey');
  });
});
