// Purpose: define serialized core-domain contracts. Responsibilities: expose typed IDs, enums, organization, repository, and profile shapes for browser consumers. Future modules: add decoy and operational contracts without changing existing semantics.
export type Brand<Value, Name extends string> = Value & { readonly __brand: Name };

export type OrganizationId = Brand<string, 'OrganizationId'>;
export type RepositoryId = Brand<string, 'RepositoryId'>;
export type RepositoryProfileId = Brand<string, 'RepositoryProfileId'>;
export type DecoyId = Brand<string, 'DecoyId'>;
export type PlacementId = Brand<string, 'PlacementId'>;
export type BelievabilityId = Brand<string, 'BelievabilityId'>;
export type AlertId = Brand<string, 'AlertId'>;
export type IncidentId = Brand<string, 'IncidentId'>;
export type TimelineEventId = Brand<string, 'TimelineEventId'>;
export type CoverageId = Brand<string, 'CoverageId'>;

export type IsoDateTime = Brand<string, 'IsoDateTime'>;

export interface EventEnvelope<Payload> {
  readonly event_type: string;
  readonly occurred_at: IsoDateTime;
  readonly schema_version: number;
  readonly payload: Payload;
}

export enum RepositoryProvider {
  GitHub = 'github',
  GitLab = 'gitlab',
  Bitbucket = 'bitbucket',
  AzureDevOps = 'azure_devops',
  SelfHostedGit = 'self_hosted_git',
  Other = 'other',
}

export enum CloudProvider {
  Aws = 'aws',
  Azure = 'azure',
  Gcp = 'gcp',
  Cloudflare = 'cloudflare',
  DigitalOcean = 'digitalocean',
  Other = 'other',
  Unknown = 'unknown',
}

export enum EnvironmentVariableStyle {
  UpperSnakeCase = 'upper_snake_case',
  LowerSnakeCase = 'lower_snake_case',
  KebabCase = 'kebab_case',
  Mixed = 'mixed',
  Unknown = 'unknown',
}

export enum RiskLevel {
  Low = 'low',
  Medium = 'medium',
  High = 'high',
  Critical = 'critical',
}

export enum DecoyKind {
  Secret = 'secret',
  DatabaseRecord = 'database_record',
  Document = 'document',
  SpreadsheetRow = 'spreadsheet_row',
  McpConfig = 'mcp_config',
  Embedding = 'embedding',
  AgentAsset = 'agent_asset',
}

export enum DecoyState {
  Draft = 'draft',
  Active = 'active',
  Retired = 'retired',
}

export enum Priority {
  Low = 'low',
  Normal = 'normal',
  High = 'high',
  Critical = 'critical',
}

export enum PlacementTargetKind {
  RepositoryPath = 'repository_path',
  DatabaseTable = 'database_table',
  DocumentStore = 'document_store',
  Spreadsheet = 'spreadsheet',
  McpServer = 'mcp_server',
  VectorIndex = 'vector_index',
  AgentWorkspace = 'agent_workspace',
}

export enum DocumentFormat {
  Text = 'text',
  Markdown = 'markdown',
  Pdf = 'pdf',
  Docx = 'docx',
}

export enum McpTransport {
  Stdio = 'stdio',
  Sse = 'sse',
  StreamableHttp = 'streamable_http',
}

export enum AgentAssetKind {
  Instruction = 'instruction',
  ToolDefinition = 'tool_definition',
  Memory = 'memory',
  Skill = 'skill',
}

export enum Severity {
  Info = 'info',
  Low = 'low',
  Medium = 'medium',
  High = 'high',
  Critical = 'critical',
}

export enum DetectionSource {
  Repository = 'repository',
  Database = 'database',
  Document = 'document',
  Browser = 'browser',
  Agent = 'agent',
  Mcp = 'mcp',
  System = 'system',
}

export enum TriggerType {
  DecoyAccessed = 'decoy_accessed',
  UnexpectedAccess = 'unexpected_access',
  PolicyViolation = 'policy_violation',
  AnomalousBehavior = 'anomalous_behavior',
  IntegrityChange = 'integrity_change',
}

export enum DetectionMethod {
  CanaryToken = 'canary_token',
  ContentAccess = 'content_access',
  AuditLog = 'audit_log',
  BrowserTelemetry = 'browser_telemetry',
  ToolTelemetry = 'tool_telemetry',
  DatabaseAudit = 'database_audit',
}

export enum MonitorType {
  FileContent = 'file_content',
  Repository = 'repository',
  DatabasePayload = 'database_payload',
  TextPayload = 'text_payload',
}

export enum MonitorHealthStatus {
  Active = 'active',
  Inactive = 'inactive',
  Degraded = 'degraded',
  Failed = 'failed',
}

export enum TimelineAction {
  Read = 'read',
  Copy = 'copy',
  Export = 'export',
  Paste = 'paste',
  Index = 'index',
  Embed = 'embed',
  Authentication = 'authentication',
  ToolCall = 'tool_call',
  DatabaseQuery = 'database_query',
  PackageInstall = 'package_install',
  DocumentAccess = 'document_access',
}

export interface TechnologyEvidence {
  readonly name: string;
  readonly confidence: number;
  readonly evidence: readonly string[];
}

export interface RiskArea {
  readonly category: string;
  readonly severity: RiskLevel;
  readonly confidence: number;
  readonly explanation: string;
}

export interface NamingPattern {
  readonly scope: string;
  readonly expression: string;
  readonly sample_count: number;
  readonly confidence: number;
}

export interface RepositoryStatistics {
  readonly file_count: number;
  readonly line_count: number;
  readonly commit_count: number;
  readonly contributor_count: number;
  readonly dependency_count: number;
}

export interface Organization {
  readonly id: OrganizationId;
  readonly name: string;
  readonly slug: string;
  readonly created_at: IsoDateTime;
  readonly schema_version: number;
}

export interface Repository {
  readonly id: RepositoryId;
  readonly organization_id: OrganizationId;
  readonly provider: RepositoryProvider;
  readonly provider_repository_id: string;
  readonly canonical_url: string;
  readonly default_branch: string;
  readonly created_at: IsoDateTime;
  readonly updated_at: IsoDateTime;
  readonly schema_version: number;
}

export interface RepositoryProfile {
  readonly id: RepositoryProfileId;
  readonly repository_id: RepositoryId;
  readonly repository_revision: string;
  readonly generated_at: IsoDateTime;
  readonly languages: readonly TechnologyEvidence[];
  readonly frameworks: readonly TechnologyEvidence[];
  readonly services: readonly TechnologyEvidence[];
  readonly infrastructure: readonly TechnologyEvidence[];
  readonly cloud_provider: CloudProvider;
  readonly environment_variable_style: EnvironmentVariableStyle;
  readonly statistics: RepositoryStatistics;
  readonly detected_technologies: readonly TechnologyEvidence[];
  readonly risk_areas: readonly RiskArea[];
  readonly naming_patterns: readonly NamingPattern[];
  readonly schema_version: number;
}

export enum NamingCategory {
  EnvironmentVariable = 'environment_variable',
  Service = 'service',
  Database = 'database',
  File = 'file',
  Folder = 'folder',
  Api = 'api',
  Resource = 'resource',
}

export enum NamingStyle {
  ScreamingSnake = 'screaming_snake',
  Snake = 'snake',
  Kebab = 'kebab',
  Dot = 'dot',
  Camel = 'camel',
  Pascal = 'pascal',
  FlatLower = 'flat_lower',
  FlatUpper = 'flat_upper',
}

export interface NamingConvention {
  readonly category: NamingCategory;
  readonly style: NamingStyle;
  readonly separator: string;
  readonly support: number;
  readonly confidence: number;
  readonly samples: readonly string[];
}

export interface NamingProfile {
  readonly naming_style: readonly NamingConvention[];
  readonly common_prefixes: readonly string[];
  readonly common_suffixes: readonly string[];
  readonly vocabulary: readonly { readonly value: string; readonly support: number }[];
  readonly confidence: number;
}

export interface OrganizationContextProfile {
  readonly repository_name: string;
  readonly organization_archetype: string;
  readonly stack_maturity: string;
  readonly primary_technical_vocabulary: NamingProfile['vocabulary'];
  readonly likely_sensitive_asset_types: readonly string[];
  readonly ai_exposure_risk: number;
  readonly database_sensitivity_confidence: number;
  readonly documentation_culture: string;
  readonly operational_complexity: string;
  readonly confidence: number;
}

export enum PlacementTargetType {
  AgentAccessibleFolder = 'agent_accessible_folder',
  ArchitectureDocument = 'architecture_document',
  BrowserAiWorkflow = 'browser_ai_workflow',
  CiCdFile = 'ci_cd_file',
  ConfigFile = 'config_file',
  DatabaseRow = 'database_row',
  DocumentationFile = 'documentation_file',
  EnvironmentFile = 'environment_file',
  ExampleEnvironmentFile = 'example_environment_file',
  ExportableReport = 'exportable_report',
  InternalWikiPage = 'internal_wiki_page',
  LegacyScript = 'legacy_script',
  McpConfig = 'mcp_config',
  RagDocument = 'rag_document',
  SpreadsheetRow = 'spreadsheet_row',
}

export interface PlacementRecommendation {
  readonly target_type: PlacementTargetType;
  readonly target_location: string;
  readonly placement_priority: number;
  readonly confidence: number;
  readonly reasoning: readonly string[];
  readonly expected_detection_quality: number;
  readonly risk_score: number;
  readonly expected_attacker_agent_visibility: number;
  readonly expected_false_positive_risk: number;
  readonly future_asset_type_recommendation: DecoyKind;
  readonly evidence: readonly string[];
}

export interface RejectedPlacementCandidate {
  readonly target_type: PlacementTargetType;
  readonly target_location: string;
  readonly rejection_reasons: readonly string[];
}

export interface PlacementPlan {
  readonly repository_name: string;
  readonly context: OrganizationContextProfile;
  readonly recommendations: readonly PlacementRecommendation[];
  readonly rejected_candidates: readonly RejectedPlacementCandidate[];
}

export enum DecoyTemplateId {
  SecretV1 = 'secret_v1',
  DocumentV1 = 'document_v1',
  DatabaseRecordV1 = 'database_record_v1',
}

export interface BelievabilityInputs {
  readonly naming_match: number;
  readonly entropy_profile: number;
  readonly context_match: number;
  readonly placement_match: number;
  readonly schema_realism: number;
  readonly business_realism: number;
  readonly safety_risk: number;
}

export interface DecoyValidationResult {
  readonly valid: boolean;
  readonly checks: readonly string[];
  readonly reasons: readonly string[];
}

export interface DecoyAsset {
  readonly decoy_id: string;
  readonly decoy_type: DecoyKind;
  readonly target_placement_id: string;
  readonly target_location: string;
  readonly payload: Record<string, unknown>;
  readonly template_id: DecoyTemplateId;
  readonly believability_inputs: BelievabilityInputs;
  readonly safety_metadata: {
    readonly contains_real_credentials: false;
    readonly contains_real_customer_data: false;
    readonly safe_for_demo: true;
    readonly authentication_capability: 'none';
  };
  readonly collision_check: {
    readonly checked_names: readonly string[];
    readonly collision_detected: boolean;
    readonly reasons: readonly string[];
  };
  readonly trigger_metadata: {
    readonly trace_identifier: string;
    readonly monitoring_status: 'not_configured';
  };
  readonly rotation_metadata: {
    readonly expires_at: string | null;
    readonly rotation_recommendation: string;
  };
  readonly explanation: readonly string[];
  readonly validation: DecoyValidationResult;
}

export interface DecoyGenerationPlan {
  readonly repository_name: string;
  readonly assets: readonly DecoyAsset[];
  readonly rejected_candidates: readonly {
    readonly target_location: string;
    readonly reasons: readonly string[];
  }[];
}

export enum BelievabilityDecision {
  Accept = 'accept',
  Warn = 'warn',
  Reject = 'reject',
}

export interface BelievabilityScoreBreakdown {
  readonly naming_realism: number;
  readonly context_fit: number;
  readonly placement_compatibility: number;
  readonly schema_completeness: number;
  readonly entropy_realism: number;
  readonly business_realism: number;
  readonly traceability_quality: number;
  readonly safety_inertness: number;
  readonly production_collision_risk: number;
  readonly accidental_use_risk: number;
  readonly obvious_trap_risk: number;
}

export interface BelievabilitySafetyReport {
  readonly decoy_id: string;
  readonly overall_believability_score: number;
  readonly overall_safety_score: number;
  readonly decision: BelievabilityDecision;
  readonly breakdown: BelievabilityScoreBreakdown;
  readonly explainability_notes: readonly string[];
  readonly failed_checks: readonly string[];
  readonly warnings: readonly string[];
  readonly recommended_fixes: readonly string[];
}

export interface ContentReference {
  readonly locator: string;
  readonly sha256: string;
  readonly media_type: string;
}

export interface DecoyField {
  readonly name: string;
  readonly data_type: string;
  readonly display_value: string;
}

export interface SecretPayload {
  readonly kind: DecoyKind.Secret;
  readonly secret_kind: string;
  readonly redacted_value: string;
  readonly fingerprint: string;
  readonly content: ContentReference;
}

export interface DatabaseRecordPayload {
  readonly kind: DecoyKind.DatabaseRecord;
  readonly schema_name: string;
  readonly table_name: string;
  readonly primary_key_hint: string;
  readonly fields: readonly DecoyField[];
  readonly content: ContentReference;
}

export interface DocumentPayload {
  readonly kind: DecoyKind.Document;
  readonly filename: string;
  readonly format: DocumentFormat;
  readonly title: string;
  readonly content: ContentReference;
}

export interface SpreadsheetRowPayload {
  readonly kind: DecoyKind.SpreadsheetRow;
  readonly workbook_name: string;
  readonly sheet_name: string;
  readonly row_index: number;
  readonly fields: readonly DecoyField[];
  readonly content: ContentReference;
}

export interface McpConfigPayload {
  readonly kind: DecoyKind.McpConfig;
  readonly server_name: string;
  readonly transport: McpTransport;
  readonly redacted_endpoint: string;
  readonly content: ContentReference;
}

export interface EmbeddingPayload {
  readonly kind: DecoyKind.Embedding;
  readonly index_name: string;
  readonly dimensions: number;
  readonly content: ContentReference;
}

export interface AgentAssetPayload {
  readonly kind: DecoyKind.AgentAsset;
  readonly asset_kind: AgentAssetKind;
  readonly name: string;
  readonly description: string;
  readonly content: ContentReference;
}

export type DecoyPayload =
  | SecretPayload
  | DatabaseRecordPayload
  | DocumentPayload
  | SpreadsheetRowPayload
  | McpConfigPayload
  | EmbeddingPayload
  | AgentAssetPayload;

export interface Decoy {
  readonly id: DecoyId;
  readonly organization_id: OrganizationId;
  readonly repository_id: RepositoryId | null;
  readonly repository_profile_id: RepositoryProfileId | null;
  readonly state: DecoyState;
  readonly payload: DecoyPayload;
  readonly schema_version: number;
}

export interface PlacementTarget {
  readonly kind: PlacementTargetKind;
  readonly locator: string;
  readonly repository_id: RepositoryId | null;
}

export interface Placement {
  readonly id: PlacementId;
  readonly decoy_id: DecoyId;
  readonly target: PlacementTarget;
  readonly confidence: number;
  readonly reason: string;
  readonly priority: Priority;
  readonly risk: RiskLevel;
  readonly expected_detection_quality: number;
  readonly schema_version: number;
}

export interface Believability {
  readonly id: BelievabilityId;
  readonly decoy_id: DecoyId;
  readonly naming_score: number;
  readonly entropy_score: number;
  readonly context_score: number;
  readonly schema_score: number;
  readonly placement_score: number;
  readonly overall_score: number;
  readonly explainability: string;
  readonly schema_version: number;
}

export interface EventAttribute {
  readonly key: string;
  readonly value: string;
}

export interface AssetReference {
  readonly kind: string;
  readonly asset_id: string;
  readonly label: string;
}

export interface EvidenceReference {
  readonly kind: string;
  readonly locator: string;
  readonly sha256: string;
  readonly summary: string;
}

export interface TimelineEvent {
  readonly id: TimelineEventId;
  readonly organization_id: OrganizationId;
  readonly action: TimelineAction;
  readonly source: DetectionSource;
  readonly timestamp: IsoDateTime;
  readonly target: AssetReference;
  readonly decoy_id: DecoyId | null;
  readonly actor_reference: string | null;
  readonly confidence: number;
  readonly attributes: readonly EventAttribute[];
  readonly schema_version: number;
}

export interface Alert {
  readonly id: AlertId;
  readonly organization_id: OrganizationId;
  readonly severity: Severity;
  readonly source: DetectionSource;
  readonly timestamp: IsoDateTime;
  readonly confidence: number;
  readonly trigger_type: TriggerType;
  readonly detection_method: DetectionMethod;
  readonly timeline_event_id: TimelineEventId;
  readonly decoy_id: DecoyId | null;
  readonly incident_id: IncidentId | null;
  readonly schema_version: number;
}

export interface Incident {
  readonly id: IncidentId;
  readonly organization_id: OrganizationId;
  readonly timeline: readonly TimelineEvent[];
  readonly root_cause: string;
  readonly affected_assets: readonly AssetReference[];
  readonly risk: RiskLevel;
  readonly summary: string;
  readonly evidence: readonly EvidenceReference[];
  readonly recommendations: readonly string[];
  readonly schema_version: number;
}

export interface Coverage {
  readonly id: CoverageId;
  readonly organization_id: OrganizationId;
  readonly repository_id: RepositoryId | null;
  readonly repository_coverage: number;
  readonly database_coverage: number;
  readonly document_coverage: number;
  readonly ai_coverage: number;
  readonly overall_coverage: number;
  readonly measured_at: IsoDateTime;
  readonly schema_version: number;
}

export interface TripwireRegistryEntry {
  readonly trace_identifier: string;
  readonly decoy_id: string;
  readonly placement_id: string;
  readonly target_location: string;
  readonly template_id: string;
  readonly decoy_type: string;
  readonly enabled: boolean;
}

export interface RawDetectionEvent {
  readonly event_id: string;
  readonly trace_identifier: string;
  readonly decoy_id: string;
  readonly monitor_type: MonitorType;
  readonly observed_location: string;
  readonly observed_value_excerpt: string;
  readonly timestamp: IsoDateTime;
  readonly source: DetectionSource;
  readonly confidence: number;
  readonly severity_suggestion: Severity;
  readonly evidence_digest: string;
  readonly detection_method: DetectionMethod;
  readonly correlation_id: string;
}

export enum AlertStatus {
  Open = 'open',
  Acknowledged = 'acknowledged',
  Closed = 'closed',
}

export interface NormalizedAlert {
  readonly alert_id: string;
  readonly trace_identifier: string;
  readonly decoy_id: string;
  readonly severity: Severity;
  readonly status: AlertStatus;
  readonly title: string;
  readonly summary: string;
  readonly source_monitor: MonitorType;
  readonly confidence: number;
  readonly first_seen: IsoDateTime;
  readonly last_seen: IsoDateTime;
  readonly event_count: number;
  readonly deduplication_key: string;
  readonly affected_placement_id: string;
  readonly affected_decoy_type: string;
  readonly recommended_actions: readonly string[];
  readonly correlation_id: string;
}

export interface RepositoryScanner {
  scan(repository: Repository): Promise<RepositoryProfile>;
}

export interface ProfileGenerator {
  generate(repository: Repository): Promise<RepositoryProfile>;
}

export interface DecoyGenerator {
  generate(profile: RepositoryProfile): Promise<Decoy>;
}

export interface PlacementEngine {
  assess(decoy: Decoy, profile: RepositoryProfile): Promise<Placement>;
}

export interface BelievabilityEngine {
  assess(decoy: Decoy, placement: Placement): Promise<Believability>;
}

export interface MonitoringEngine {
  evaluate(event: TimelineEvent): Promise<Alert | null>;
}

export interface IncidentEngine {
  assess(alerts: readonly Alert[]): Promise<Incident | null>;
}

export interface CoverageEngine {
  measure(profile: RepositoryProfile): Promise<Coverage>;
}

export interface PromptEngine {
  resolve(promptName: string, version: string): Promise<string>;
}

export interface BrowserMonitor {
  observe(payload: Uint8Array): Promise<TimelineEvent | null>;
}

export interface DatabaseMonitor {
  observe(payload: Uint8Array): Promise<TimelineEvent | null>;
}

// ---- Demo dashboard aggregate contract ----
// Shape of the /demo/state payload. Fields mirror the demo API; enums are reused so the frontend
// stops re-declaring weak string unions and cannot drift from the backend vocabulary.

export interface DemoTechnologyEvidence {
  readonly name: string;
  readonly confidence: number;
  readonly evidence: readonly string[];
}

export interface DemoNamingConvention {
  readonly category: NamingCategory;
  readonly style: NamingStyle;
  readonly separator: string;
  readonly confidence: number;
  readonly samples: readonly string[];
}

export interface DemoNamingProfile {
  readonly naming_style: readonly DemoNamingConvention[];
  readonly common_prefixes: readonly string[];
  readonly common_suffixes: readonly string[];
  readonly confidence: number;
}

export interface DemoRiskArea {
  readonly category: string;
  readonly severity: Severity;
  readonly description: string;
  readonly paths: readonly string[];
}

export interface DemoRepositoryProfileSummary {
  readonly repository_name: string;
  readonly file_count: number;
  readonly is_git_repository: boolean;
  readonly languages: readonly DemoTechnologyEvidence[];
  readonly frameworks: readonly DemoTechnologyEvidence[];
  readonly services: readonly DemoTechnologyEvidence[];
  readonly package_managers: readonly DemoTechnologyEvidence[];
  readonly databases: readonly DemoTechnologyEvidence[];
  readonly cloud_providers: readonly DemoTechnologyEvidence[];
  readonly cicd: readonly DemoTechnologyEvidence[];
  readonly documentation: readonly DemoTechnologyEvidence[];
  readonly mcp_configurations: readonly DemoTechnologyEvidence[];
  readonly infrastructure: {
    readonly docker_files: readonly string[];
    readonly kubernetes_files: readonly string[];
    readonly terraform_files: readonly string[];
  };
  readonly naming_profile: DemoNamingProfile | null;
  readonly secret_locations: readonly { readonly path: string; readonly patterns: readonly string[] }[];
  readonly risk_areas: readonly DemoRiskArea[];
  readonly truncated: boolean;
}

export interface DemoContextSummary {
  readonly organization_archetype: string;
  readonly stack_maturity: string;
  readonly documentation_culture: string;
  readonly operational_complexity: string;
  readonly ai_exposure_risk: number;
  readonly database_sensitivity_confidence: number;
  readonly environment_naming_conventions: readonly string[];
  readonly likely_sensitive_asset_types: readonly string[];
  readonly confidence: number;
}

export interface DemoPlacementSummary {
  readonly target_type: PlacementTargetType;
  readonly target_location: string;
  readonly placement_priority: number;
  readonly confidence: number;
  readonly risk_score: number;
  readonly expected_detection_quality: number;
  readonly expected_attacker_agent_visibility: number;
  readonly expected_false_positive_risk: number;
  readonly future_asset_type_recommendation: DecoyKind;
  readonly reasoning: readonly string[];
}

export interface DemoPlacementPlanSummary {
  readonly recommendations: readonly DemoPlacementSummary[];
  readonly rejected_candidates: readonly {
    readonly target_type: string;
    readonly target_location: string;
    readonly rejection_reasons: readonly string[];
  }[];
}

export interface DemoDecoySummary {
  readonly decoy_id: string;
  readonly decoy_type: DecoyKind;
  readonly target_location: string;
  readonly target_placement_id: string;
  readonly template_id: DecoyTemplateId;
  readonly payload: Record<string, unknown>;
  readonly safety_metadata: {
    readonly contains_real_credentials: boolean;
    readonly contains_real_customer_data: boolean;
    readonly safe_for_demo: boolean;
    readonly authentication_capability: string;
  };
  readonly trigger_metadata: { readonly trace_identifier: string; readonly monitoring_status: string };
  readonly validation: {
    readonly valid: boolean;
    readonly checks: readonly string[];
    readonly reasons: readonly string[];
  };
  readonly explanation: readonly string[];
}

export interface DemoDecoyPlanSummary {
  readonly repository_name: string;
  readonly assets: readonly DemoDecoySummary[];
  readonly rejected_candidates: readonly {
    readonly target_location: string;
    readonly reasons: readonly string[];
  }[];
}

export interface DemoValidationSummary {
  readonly decoy_id: string;
  readonly overall_believability_score: number;
  readonly overall_safety_score: number;
  readonly decision: BelievabilityDecision;
  readonly breakdown: Record<string, number>;
  readonly explainability_notes: readonly string[];
  readonly failed_checks: readonly string[];
  readonly warnings: readonly string[];
  readonly recommended_fixes: readonly string[];
}

export interface DemoMonitoringEventSummary {
  readonly event_id: string;
  readonly trace_identifier: string;
  readonly decoy_id: string;
  readonly monitor_type: MonitorType;
  readonly observed_location: string;
  readonly observed_value_excerpt: string;
  readonly timestamp: string;
  readonly confidence: number;
  readonly severity_suggestion: Severity;
  readonly detection_method: DetectionMethod;
}

export interface DemoAlertSummary {
  readonly alert_id: string;
  readonly trace_identifier: string;
  readonly decoy_id: string;
  readonly severity: Severity;
  readonly title: string;
  readonly summary: string;
  readonly source_monitor: MonitorType;
  readonly confidence: number;
  readonly event_count: number;
  readonly first_seen: string;
  readonly last_seen: string;
  readonly recommended_actions: readonly string[];
}

export interface DemoTimelineEntry {
  readonly sequence: number;
  readonly timestamp: string;
  readonly source: string;
  readonly monitor_type: MonitorType;
  readonly summary: string;
  readonly confidence: number;
  readonly evidence: { readonly excerpt: string; readonly digest: string; readonly location: string };
}

export interface DemoIncidentSummary {
  readonly incident_id: string;
  readonly title: string;
  readonly severity: Severity;
  readonly incident_type: string;
  readonly confidence: number;
  readonly first_seen: string;
  readonly last_seen: string;
  readonly involved_decoy_ids: readonly string[];
  readonly involved_trace_ids: readonly string[];
  readonly affected_surfaces: readonly string[];
  readonly timeline: readonly DemoTimelineEntry[];
  readonly root_cause_hypothesis: string;
  readonly recommended_actions: readonly string[];
}

export interface DemoCoverageSummary {
  readonly repository: number;
  readonly database: number;
  readonly document: number;
  readonly ai: number;
  readonly overall: number;
}

export interface DemoOverviewSummary {
  readonly total_decoys: number;
  readonly accepted_decoys: number;
  readonly active_tripwires: number;
  readonly monitor_events: number;
  readonly alerts: number;
  readonly incidents: number;
  readonly coverage: DemoCoverageSummary;
}

export interface DemoState {
  readonly repository_id: string | null;
  readonly decoy_plan_id: string | null;
  readonly profile: DemoRepositoryProfileSummary | null;
  readonly context: DemoContextSummary | null;
  readonly placement_plan: DemoPlacementPlanSummary | null;
  readonly decoy_plan: DemoDecoyPlanSummary | null;
  readonly reports: readonly DemoValidationSummary[];
  readonly events: readonly DemoMonitoringEventSummary[];
  readonly alerts: readonly DemoAlertSummary[];
  readonly incidents: readonly DemoIncidentSummary[];
  readonly overview: DemoOverviewSummary;
}

// ---- Demo orchestration (one-click run) ----

export interface CoverageSummary {
  readonly repository: number;
  readonly placement: number;
  readonly decoy_activation: number;
  readonly monitoring: number;
  readonly alerting: number;
  readonly incident: number;
  readonly ai_narrative: number;
  readonly overall: number;
}

export enum DemoRunStepStatus {
  Pending = 'pending',
  Running = 'running',
  Complete = 'complete',
  Failed = 'failed',
}

export interface DemoRunStep {
  readonly key: string;
  readonly label: string;
  readonly status: DemoRunStepStatus;
  readonly note: string | null;
}

export enum DemoRunStatus {
  Complete = 'complete',
  Failed = 'failed',
}

export interface DemoRun {
  readonly run_id: string;
  readonly created_at: string;
  readonly status: DemoRunStatus;
  readonly steps: readonly DemoRunStep[];
  readonly coverage: CoverageSummary;
  readonly narrative: IncidentNarrative | null;
  readonly state: DemoState;
}

// ---- GPT incident narrative (optional, never overrides deterministic incident data) ----

export enum NarrativeSource {
  Model = 'model',
  Fallback = 'fallback',
}

export enum NarrativeStatus {
  Generated = 'generated',
  FallbackDisabled = 'fallback_disabled',
  FallbackError = 'fallback_error',
  FallbackInvalid = 'fallback_invalid',
}

export interface NarrativeTokenUsage {
  readonly prompt_tokens: number;
  readonly completion_tokens: number;
  readonly total_tokens: number;
}

export interface IncidentNarrativeBody {
  readonly executive_summary: string;
  readonly analyst_summary: string;
  readonly likely_sequence: readonly string[];
  readonly evidence_summary: readonly string[];
  readonly recommended_next_actions: readonly string[];
  readonly uncertainty_caveats: readonly string[];
  readonly confidence_notes: string;
}

export interface IncidentNarrative {
  readonly narrative_id: string;
  readonly incident_id: string;
  readonly organization_id: string;
  readonly revision_number: number;
  readonly source: NarrativeSource;
  readonly status: NarrativeStatus;
  readonly model: string | null;
  readonly prompt_version: string;
  readonly source_context_hash: string;
  readonly created_at: string;
  readonly body: IncidentNarrativeBody;
  readonly token_usage: NarrativeTokenUsage | null;
  readonly error: string | null;
}
