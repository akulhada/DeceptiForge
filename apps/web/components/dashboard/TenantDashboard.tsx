// Purpose: the production-like tenant dashboard (authenticated, no demo routes).
// Responsibilities: gate on a connection, load organization-scoped data, and render the pipeline
//   sections without any seed/simulate/demo controls. Dependencies: connect panel, tenant hook.
'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AgentSensorPanel } from '@/components/dashboard/AgentSensorPanel';
import { AiTripwirePanel } from '@/components/dashboard/AiTripwirePanel';
import { CoveragePanel } from '@/components/dashboard/CoveragePanel';
import { IntegrationsPanel } from '@/components/dashboard/IntegrationsPanel';
import { OnboardingPanel } from '@/components/dashboard/OnboardingPanel';
import { ReliabilityPanel } from '@/components/dashboard/ReliabilityPanel';
import { BrowserSensorPanel } from '@/components/dashboard/BrowserSensorPanel';
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
import { tenantApi } from '@/services/tenantApi';

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
            {whoami?.scopes.includes('onboarding:read') && (
              <OnboardingPanel scopes={whoami.scopes} />
            )}
            <RepositoryProfileSection profile={state.profile} context={state.context} />
            <PlacementSection plan={state.placement_plan} />
            <DecoySection plan={state.decoy_plan} />
            <ValidationSection reports={state.reports} />
            <MonitoringSection events={state.events} />
            <AlertsSection alerts={state.alerts} />
            <IncidentsSection
              incidents={state.incidents}
              generateNarrative={tenantApi.generateIncidentNarrative}
            />
            {whoami?.scopes.includes('decoy_deployments:read') && (
              <DeploymentsPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('database_honey:read') && (
              <DatabaseHoneyPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('ai_tripwires:read') && (
              <AiTripwirePanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('browser_sensors:read') && (
              <BrowserSensorPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('agent_sensors:read') && (
              <AgentSensorPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('coverage:read') && (
              <CoveragePanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('integrations:read') && (
              <IntegrationsPanel scopes={whoami.scopes} />
            )}
            {whoami?.scopes.includes('reliability:read') && (
              <ReliabilityPanel scopes={whoami.scopes} />
            )}
          </>
        ) : null}
      </main>
    </div>
  );
}

// After connecting, honor a `?next=` return path (e.g. from the Analysis Lab) — but only a
// same-origin absolute path, never a protocol-relative or external URL.
function handleConnected(setConnected: (value: boolean) => void): () => void {
  return () => {
    const next = new URLSearchParams(window.location.search).get('next');
    if (next && next.startsWith('/') && !next.startsWith('//')) {
      window.location.assign(next);
      return;
    }
    setConnected(true);
  };
}

export function TenantDashboard() {
  // The session lives in sessionStorage, which does not exist during server rendering. Seeding this
  // from getSession() made the server render the connect panel while the client rendered the
  // connected dashboard, so React discarded the server tree and warned about a hydration mismatch.
  // Start disconnected — matching what the server can know — and read the session after mount.
  const [connected, setConnected] = useState(false);
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    setConnected(getSession() !== null);
    setRestored(true);
  }, []);

  // Render nothing until the session has been read, so a stored session does not flash the connect
  // panel for a frame before the dashboard appears.
  if (!restored) return null;

  if (!connected) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-16">
        <ConnectPanel onConnected={handleConnected(setConnected)} />
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
