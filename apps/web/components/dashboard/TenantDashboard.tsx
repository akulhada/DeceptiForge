// Purpose: the production-like tenant dashboard (authenticated, no demo routes).
// Responsibilities: gate on a connection, load organization-scoped data, and render the pipeline
//   sections without any seed/simulate/demo controls. Dependencies: connect panel, tenant hook.
'use client';

import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AiTripwirePanel } from '@/components/dashboard/AiTripwirePanel';
import { ConnectPanel } from '@/components/dashboard/ConnectPanel';
import { DatabaseHoneyPanel } from '@/components/dashboard/DatabaseHoneyPanel';
import { DeploymentsPanel } from '@/components/dashboard/DeploymentsPanel';
import { ErrorState, LoadingState } from '@/components/dashboard/states';
import {
  AlertsSection,
  DecoySection,
  IncidentsSection,
  MonitoringSection,
  OverviewSection,
  PlacementSection,
  RepositoryProfileSection,
  ValidationSection,
} from '@/components/dashboard/sections';
import { useTenantDashboardData } from '@/hooks/useTenantDashboardData';
import { clearSession, getSession } from '@/services/authSession';

function ConnectedTenant({ onDisconnect }: { onDisconnect: () => void }) {
  const { state, whoami, loading, error, refetch } = useTenantDashboardData();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/80 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">DeceptiForge</h1>
            <p className="text-xs text-slate-500">
              Tenant console{whoami ? ` · org ${whoami.organization_id.slice(0, 8)} · ${whoami.role}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="info">tenant mode</Badge>
            <Button variant="secondary" size="sm" onClick={() => void refetch()}>
              Refresh
            </Button>
            <Button variant="ghost" size="sm" onClick={onDisconnect}>
              Disconnect
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-10 px-6 py-8">
        {loading && state === null ? (
          <LoadingState />
        ) : error ? (
          <ErrorState
            message={error}
            action={
              <Button variant="secondary" onClick={() => void refetch()}>
                Retry
              </Button>
            }
          />
        ) : state ? (
          <>
            <OverviewSection overview={state.overview} />
            <RepositoryProfileSection profile={state.profile} context={state.context} />
            <PlacementSection plan={state.placement_plan} />
            <DecoySection plan={state.decoy_plan} />
            <ValidationSection reports={state.reports} />
            <MonitoringSection events={state.events} />
            <AlertsSection alerts={state.alerts} />
            <IncidentsSection incidents={state.incidents} />
            {whoami?.scopes.includes('decoy_deployments:read') && (
              <DeploymentsPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('database_honey:read') && (
              <DatabaseHoneyPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('ai_tripwires:read') && (
              <AiTripwirePanel scopes={whoami.scopes} />
            )}
          </>
        ) : null}
      </main>
    </div>
  );
}

export function TenantDashboard() {
  const [connected, setConnected] = useState(() => getSession() !== null);
  if (!connected) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-16">
        <ConnectPanel onConnected={() => setConnected(true)} />
      </div>
    );
  }
  return (
    <ConnectedTenant
      onDisconnect={() => {
        clearSession();
        setConnected(false);
      }}
    />
  );
}
