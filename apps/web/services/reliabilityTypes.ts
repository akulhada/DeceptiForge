// Purpose: types for the reliability / disaster-recovery admin surface.
// Responsibilities: mirror the backend contracts (status, dependencies, drills, failover events).
//   No behavior. Never carries infrastructure credentials.

export interface RegionIdentity {
  deployment_region: string;
  cluster_id: string;
  environment: string;
  role: 'primary' | 'standby' | 'recovery';
  deployment_revision: string;
  database_cluster_id: string;
  active_region_epoch: number;
  secondary_region: string | null;
  dr_enabled: boolean;
  maintenance_mode: boolean;
}

export interface LatestRestore {
  backup_identifier: string;
  passed: boolean;
  achieved_rpo_minutes: number | null;
  achieved_rto_minutes: number | null;
  created_at: string;
}

export interface ReliabilityStatus {
  region: RegionIdentity;
  failover_state: string;
  recovery_objectives: Record<
    string,
    { data_class: string; rpo_minutes: number; rto_minutes: number; recomputable: boolean }
  >;
  latest_verified_restore: LatestRestore | null;
  maintenance_mode: boolean;
}

export interface DependencyStatus {
  database: { status: string };
  redis: { status: string };
  encryption: { status: string };
  replay_protection: { required: boolean; status: string };
  active_region: { role: string; is_active_write_region: boolean; epoch: number };
  maintenance_mode: boolean;
}

export interface RestoreDrill {
  id: string;
  backup_identifier: string;
  passed: boolean;
  achieved_rpo_minutes: number | null;
  achieved_rto_minutes: number | null;
  checksum: string;
  created_at: string;
}

export interface FailoverEvent {
  id: string;
  from_state: string;
  to_state: string;
  deployment_region: string;
  active_region_epoch: number;
  reason: string;
  created_at: string;
}
