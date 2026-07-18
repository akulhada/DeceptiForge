// Purpose: the DeceptiForge demo dashboard entry point.
// Responsibilities: load aggregate state, drive the seed/simulate demo flow, and render the eight
//   sections as one scrollable security-console story. Dependencies: dashboard hooks and sections.
'use client';

import { useDashboardData } from '@/hooks/useDashboardData';
import { useDemoFlow } from '@/hooks/useDemoFlow';
import { Button } from '@/components/ui/button';
import { DemoRunButton } from '@/components/dashboard/DemoRunButton';
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

const NAV = [
  ['overview', 'Overview'],
  ['repository', 'Repository'],
  ['placements', 'Placements'],
  ['decoys', 'Decoys'],
  ['validation', 'Validation'],
  ['monitoring', 'Monitoring'],
  ['alerts', 'Alerts'],
  ['incidents', 'Incidents'],
] as const;

export default function DashboardPage() {
  const { state, loading, error, setState, refetch } = useDashboardData();
  const { seed, simulate, seeding, simulating, actionError } = useDemoFlow(setState);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">DeceptiForge</h1>
            <p className="text-xs text-slate-500">Context-aware deception platform · demo console</p>
          </div>
          <DemoRunButton
            onSeed={seed}
            onSimulate={simulate}
            seeding={seeding}
            simulating={simulating}
            canSimulate={(state?.overview.accepted_decoys ?? 0) > 0}
          />
        </div>
        <nav className="mx-auto flex max-w-7xl gap-4 overflow-x-auto px-6 pb-2 text-xs text-slate-400">
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="whitespace-nowrap hover:text-sky-400">
              {label}
            </a>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl space-y-10 px-6 py-8">
        {actionError ? (
          <div className="rounded-lg border border-red-900/60 bg-red-950/30 px-4 py-2 text-sm text-red-300">
            {actionError}
          </div>
        ) : null}

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
          </>
        ) : null}
      </main>
    </div>
  );
}
