// Purpose: tenant-scoped guided-onboarding API client; never uses demo endpoints or env credentials.
'use client';

import { getSession } from './authSession';

export interface OnboardingStep {
  phase: string;
  step_key: string;
  status: string;
  safe_blocked_message: string | null;
}

export interface OnboardingWorkspace {
  status: string;
  current_phase: string;
  activated: boolean;
  steps: OnboardingStep[];
}

async function request<T>(path: string, method = 'GET'): Promise<T> {
  const session = getSession();
  if (!session) throw new Error('not connected');
  const response = await fetch(`${session.baseUrl}${path}`, {
    method,
    headers: { 'content-type': 'application/json', 'X-DeceptiForge-Org-Id': session.organizationId, 'X-DeceptiForge-API-Key': session.apiKey },
  });
  if (!response.ok) throw new Error(`Onboarding request failed (${response.status}).`);
  return response.json() as Promise<T>;
}

export const onboardingApi = {
  get: () => request<OnboardingWorkspace>('/onboarding'),
  start: () => request<OnboardingWorkspace>('/onboarding/start', 'POST'),
  recalculate: () => request<OnboardingWorkspace>('/onboarding/recalculate', 'POST'),
};
