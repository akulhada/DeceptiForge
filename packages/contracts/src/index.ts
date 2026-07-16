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
