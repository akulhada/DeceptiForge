// Purpose: drive the demo actions (seed, simulate detection) that advance the story.
// Responsibilities: run each action, surface its pending state, push the returned state back into
//   the dashboard, and report action errors. Dependencies: the API client.
'use client';

import { useCallback, useState } from 'react';

import { api, ApiError } from '@/services/api';
import type { DemoState } from '@/services/types';

interface DemoFlow {
  seed: () => Promise<void>;
  simulate: () => Promise<void>;
  seeding: boolean;
  simulating: boolean;
  actionError: string | null;
}

export function useDemoFlow(onState: (next: DemoState) => void): DemoFlow {
  const [seeding, setSeeding] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = useCallback(
    async (action: () => Promise<DemoState>, setPending: (value: boolean) => void) => {
      setPending(true);
      setActionError(null);
      try {
        onState(await action());
      } catch (caught) {
        setActionError(caught instanceof ApiError ? caught.message : 'Demo action failed.');
      } finally {
        setPending(false);
      }
    },
    [onState],
  );

  const seed = useCallback(() => run(api.seed, setSeeding), [run]);
  const simulate = useCallback(() => run(api.simulateDetection, setSimulating), [run]);

  return { seed, simulate, seeding, simulating, actionError };
}
