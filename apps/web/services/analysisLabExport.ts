// Purpose: deterministic JSON + Markdown export of an analysis result.
// Responsibilities: serialize only the response contract (never tokens, session ids, org secrets,
//   auth claims, server paths, or stack traces), and build a sanitized filename. Pure functions —
//   no DOM, no network.
import type { AnalysisPreviewResponse } from './analysisLabTypes';

export function safeFilename(scenarioName: string | null, schemaVersion: string, at: Date): string {
  const base = (scenarioName ?? 'custom-analysis')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .slice(0, 40) || 'custom-analysis';
  const stamp = at.toISOString().replace(/[:.]/g, '-').replace('T', '_').slice(0, 19);
  const version = schemaVersion.replace(/[^a-z0-9-]+/gi, '');
  return `${base}_${stamp}_${version}`;
}

export function toJson(response: AnalysisPreviewResponse): string {
  return JSON.stringify(response, null, 2);
}

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function toMarkdown(response: AnalysisPreviewResponse, scenarioName: string | null): string {
  const cp = response.context_profile;
  const lines: string[] = [];
  lines.push(`# DeceptiForge analysis — ${scenarioName ?? 'custom analysis'}`);
  lines.push('');
  lines.push(`- Schema version: \`${response.schema_version}\``);
  lines.push(`- Engine versions: ${Object.entries(response.engine_versions).map(([k, v]) => `${k} ${v}`).join(', ')}`);
  lines.push(`- Generated at: ${response.generated_at}`);
  lines.push('');

  lines.push('## Input summary');
  const s = response.input_summary;
  lines.push(`languages ${s.language_count}, frameworks ${s.framework_count}, services ${s.service_count}, databases ${s.database_count}, docs ${s.documentation_signal_count}, secrets ${s.secret_location_count}, AI surfaces ${s.ai_surface_count}, naming ${s.naming_pattern_count}`);
  if (s.ignored_fields.length) lines.push(`Ignored fields: ${s.ignored_fields.join(', ')}`);
  lines.push('');

  lines.push('## Inferred profile');
  const fields = [
    cp.probable_business_domain, cp.probable_repository_type, cp.dominant_technical_stack,
    cp.service_architecture, cp.operational_maturity, cp.data_sensitivity, cp.deployment_model,
    cp.ai_system_exposure,
  ];
  for (const f of fields) {
    lines.push(`- **${f.key}**: ${f.value} (confidence ${pct(f.confidence)}) — ${f.reason}`);
  }
  lines.push('');

  lines.push('## Vocabulary and naming');
  lines.push(`Domain terms: ${response.vocabulary.domain_terms.join(', ') || '—'}`);
  lines.push(`Service names: ${response.vocabulary.service_names.join(', ') || '—'}`);
  for (const note of response.vocabulary.influence_notes) lines.push(`- ${note}`);
  lines.push('');

  lines.push('## Sensitive zones');
  for (const z of response.sensitive_zones) {
    lines.push(`- **${z.category}** (risk ${pct(z.risk_score)}, confidence ${pct(z.confidence)}): ${z.reasoning}`);
  }
  lines.push('');

  lines.push('## Placement recommendations');
  for (const p of response.placement_recommendations) {
    lines.push(`${p.rank}. **${p.zone}** → \`${p.proposed_path_or_pattern}\` [${p.decoy_type}] (confidence ${pct(p.confidence)}) — ${p.reasoning}`);
  }
  lines.push('');

  lines.push('## Confidence');
  const c = response.confidence;
  lines.push(`overall ${pct(c.overall)}, domain ${pct(c.domain)}, vocabulary ${pct(c.vocabulary)}, sensitive-zone ${pct(c.sensitive_zone)}, placement ${pct(c.placement)}, completeness ${pct(c.completeness)}, conflict ${pct(c.conflict)}`);
  lines.push('');

  lines.push('## Warnings');
  if (response.warnings.length === 0) lines.push('None.');
  for (const w of response.warnings) lines.push(`- **${w.code}**: ${w.message} — ${w.effect}`);
  lines.push('');

  return lines.join('\n');
}
