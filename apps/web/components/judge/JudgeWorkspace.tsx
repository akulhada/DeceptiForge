// Purpose: the restricted judge workspace rendered at the root route.
// Responsibilities: render each access state explicitly, and drive the bounded workflow (scenario ->
//   analysis -> controlled interaction -> alert/incident -> export -> reset) entirely from backend
//   state. Nothing here fakes a success: every panel shows what the API returned.
// Dependencies: judgeApi, authSession, ConnectPanel, ui primitives.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ConnectPanel } from '@/components/dashboard/ConnectPanel';
import {
  type AccessState,
  type Interaction,
  type SandboxExport,
  type Workspace,
  JudgeApiError,
  judgeApi,
} from '@/services/judgeApi';

interface Failure {
  readonly state: AccessState;
  readonly message: string;
  readonly retryAfterSeconds: number | null;
}

function toFailure(error: unknown): Failure {
  if (error instanceof JudgeApiError) {
    return { state: error.state, message: error.message, retryAfterSeconds: error.retryAfterSeconds };
  }
  return { state: 'unavailable', message: 'The workspace is unavailable.', retryAfterSeconds: null };
}

export function JudgeWorkspace() {
  const [state, setState] = useState<AccessState>('loading');
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [interaction, setInteraction] = useState<Interaction | null>(null);
  const [snapshot, setSnapshot] = useState<SandboxExport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    setFailure(null);
    try {
      setWorkspace(await judgeApi.workspace());
      setState('ready');
    } catch (error) {
      const next = toFailure(error);
      setFailure(next);
      setState(next.state);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Every action re-reads the workspace afterwards, so quotas on screen always come from the
  // backend rather than from an optimistic local decrement.
  const act = useCallback(
    async (name: string, run: () => Promise<void>) => {
      setBusy(name);
      setFailure(null);
      try {
        await run();
        setWorkspace(await judgeApi.workspace());
      } catch (error) {
        setFailure(toFailure(error));
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  if (state === 'loading') return <Centered title="Opening sandbox session…" />;

  if (state === 'unauthenticated' || state === 'no-organization') {
    return (
      <Centered title="DeceptiForge judge workspace">
        <p className="mb-4 text-sm text-slate-400">
          {state === 'no-organization'
            ? 'This credential is not bound to a sandbox organization.'
            : 'Connect with the sandbox credential you were given.'}
        </p>
        <ConnectPanel onConnected={() => void load()} />
      </Centered>
    );
  }

  if (state === 'forbidden') {
    return (
      <Centered title="This credential cannot open the judge workspace">
        <p className="text-sm text-slate-400">
          It authenticated successfully but does not carry judge permissions. Tenant and platform
          credentials cannot be used here.
        </p>
      </Centered>
    );
  }

  if (state === 'expired') {
    return (
      <Centered title="This sandbox session has ended">
        <p className="text-sm text-slate-400">
          Judge sandboxes are time limited. Ask for a new sandbox credential to continue.
        </p>
      </Centered>
    );
  }

  if (state === 'unavailable' || workspace === null) {
    return (
      <Centered title="The workspace is unavailable">
        <p className="mb-4 text-sm text-slate-400">{failure?.message ?? 'Cannot reach the API.'}</p>
        <Button onClick={() => void load()}>Retry</Button>
      </Centered>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-950/80 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">{workspace.label}</h1>
        <p className="text-xs text-slate-500">
          Fictional data only · session ends {new Date(workspace.expires_at).toLocaleString()}
        </p>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {failure ? (
          <div
            role="alert"
            className="rounded-lg border border-amber-900/60 bg-amber-950/30 px-4 py-2 text-sm text-amber-300"
          >
            {failure.message}
            {failure.retryAfterSeconds !== null ? ` Retry in ${failure.retryAfterSeconds}s.` : ''}
          </div>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Session budget</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-3 gap-4 text-sm">
            {Object.entries(workspace.quotas).map(([action, quota]) => (
              <div key={action}>
                <p className="text-xs uppercase text-slate-500">{action}</p>
                <p className="text-slate-200">
                  {quota.remaining} left <span className="text-slate-500">of {quota.limit}</span>
                </p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Predefined scenarios</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {workspace.scenarios.map((scenario) => (
              <div key={scenario.id}>
                <p className="text-slate-200">{scenario.name}</p>
                <p className="text-xs text-slate-500">{scenario.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Controlled interaction</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-xs text-slate-500">
              Touches one accepted decoy in this sandbox. The alert and incident below are produced
              by the real detection pipeline, not inserted.
            </p>
            <Button
              disabled={busy !== null}
              onClick={() =>
                void act('interact', async () => {
                  setInteraction(await judgeApi.interact());
                })
              }
            >
              {busy === 'interact' ? 'Triggering…' : 'Trigger interaction'}
            </Button>
            {interaction ? (
              <dl className="grid gap-1 text-xs text-slate-400">
                <div>Event recorded: {String(interaction.event_recorded)}</div>
                <div>Alert: {interaction.alert_id ?? 'none'}</div>
                <div>Incident: {interaction.incident_id ?? 'none'}</div>
              </dl>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Export and reset</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={busy !== null}
              onClick={() =>
                void act('export', async () => {
                  setSnapshot(await judgeApi.exportSandbox());
                })
              }
            >
              {busy === 'export' ? 'Exporting…' : 'Export summary'}
            </Button>
            <Button
              variant="secondary"
              disabled={busy !== null}
              onClick={() =>
                void act('reset', async () => {
                  await judgeApi.reset();
                  setInteraction(null);
                  setSnapshot(null);
                })
              }
            >
              {busy === 'reset' ? 'Resetting…' : 'Reset sandbox'}
            </Button>
            {snapshot ? (
              <pre className="w-full overflow-x-auto rounded bg-slate-950 p-3 text-xs text-slate-400">
                {JSON.stringify(snapshot, null, 2)}
              </pre>
            ) : null}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

function Centered({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6">
      <h1 className="mb-2 text-lg font-semibold text-slate-100">{title}</h1>
      {children}
    </div>
  );
}
