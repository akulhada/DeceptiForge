// Purpose: render state-derived activation progress with accessible remediation guidance.
'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { onboardingApi, type OnboardingWorkspace } from '@/services/onboardingApi';

export function OnboardingPanel({ scopes }: { scopes: readonly string[] }) {
  const [workspace, setWorkspace] = useState<OnboardingWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true); setError(null);
    try { setWorkspace(await onboardingApi.get()); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to load onboarding.'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  return <Card><CardHeader className="flex-row items-center justify-between gap-4"><div><CardTitle>Guided activation</CardTitle><p className="mt-1 text-sm text-slate-400">Progress is validated from deployed controls, not checklist clicks.</p></div>{workspace ? <Badge tone={workspace.activated ? 'success' : 'info'}>{workspace.activated ? 'activated' : workspace.status}</Badge> : null}</CardHeader><CardContent className="space-y-3">{loading ? <p className="text-sm text-slate-400">Loading activation state…</p> : null}{error ? <p role="alert" className="text-sm text-red-300">{error}</p> : null}{workspace?.steps.map((step) => <div key={step.step_key} className="rounded border border-slate-800 p-3"><div className="flex items-center justify-between gap-3"><span className="font-medium capitalize">{step.step_key.replaceAll('_', ' ')}</span><Badge tone={step.status === 'completed' ? 'success' : 'warning'}>{step.status}</Badge></div>{step.safe_blocked_message ? <p className="mt-1 text-sm text-slate-400">{step.safe_blocked_message}</p> : null}</div>)}{scopes.includes('onboarding:manage') ? <div className="flex gap-2"><Button onClick={() => void onboardingApi.start().then(setWorkspace).catch(() => void load())}>Start onboarding</Button><Button variant="secondary" onClick={() => void onboardingApi.recalculate().then(setWorkspace).catch(() => void load())}>Refresh validation</Button></div> : null}</CardContent></Card>;
}
