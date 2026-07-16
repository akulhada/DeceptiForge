// Purpose: define serialized core-domain contracts. Responsibilities: expose typed IDs, enums, organization, repository, and profile shapes for browser consumers. Future modules: add decoy and operational contracts without changing existing semantics.
export type Brand<Value, Name extends string> = Value & { readonly __brand: Name };

export type OrganizationId = Brand<string, 'OrganizationId'>;
export type RepositoryId = Brand<string, 'RepositoryId'>;
export type RepositoryProfileId = Brand<string, 'RepositoryProfileId'>;

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
