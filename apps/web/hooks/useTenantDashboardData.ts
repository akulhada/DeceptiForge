// Purpose: load organization-scoped tenant data for the production-like dashboard.
// Responsibilities: fetch whoami, repositories, alerts, and incidents through the tenant client and
//   assemble them into the shared dashboard state (unavailable sections render empty). It never
//   calls demo routes. Dependencies: the tenant API client and shared types.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { tenantApi, TenantApiError, type WhoAmI } from '@/services/tenantApi';
import type { DemoState } from '@/services/types';

interface TenantData {
  state: DemoState | null;
  whoami: WhoAmI | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

function toState(
  repositories: Awaited<ReturnType<typeof tenantApi.repositories>>,
  alerts: Awaited<ReturnType<typeof tenantApi.alerts>>,
  incidents: Awaited<ReturnType<typeof tenantApi.incidents>>,
): DemoState {
  const first = repositories[0] ?? null;
  return {
    repository_id: first?.repository_id ?? null,
    decoy_plan_id: null,
    profile: first?.profile ?? null,
    context: null,
    placement_plan: null,
    decoy_plan: null,
    reports: [],
    events: [],
    alerts,
    incidents,
    overview: {
      total_decoys: 0,
      accepted_decoys: 0,
      active_tripwires: 0,
      monitor_events: 0,
      alerts: alerts.length,
      incidents: incidents.length,
      coverage: { repository: 0, database: 0, document: 0, ai: 0, overall: 0 },
    },
  };
}

export function useTenantDashboardData(): TenantData {
  const [state, setState] = useState<DemoState | null>(null);
  const [whoami, setWhoami] = useState<WhoAmI | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const identity = await tenantApi.whoami();
      const [repositories, alerts, incidents] = await Promise.all([
        tenantApi.repositories(),
        tenantApi.alerts(),
        tenantApi.incidents(),
      ]);
      setWhoami(identity);
      setState(toState(repositories, alerts, incidents));
    } catch (caught) {
      setError(caught instanceof TenantApiError ? caught.message : 'Failed to load tenant data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { state, whoami, loading, error, refetch };
}
