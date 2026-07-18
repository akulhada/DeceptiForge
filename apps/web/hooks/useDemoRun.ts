// Purpose: drive the one-click end-to-end demo run.
// Responsibilities: run the full pipeline, push its resulting state into the dashboard, and expose
//   running/error status plus the step-tracked run. Dependencies: the API client.
'use client';

import { useCallback, useRef, useState } from 'react';

import { api, ApiError } from '@/services/api';
import type { DemoRun, DemoState } from '@/services/types';

interface DemoRunFlow {
  run: DemoRun | null;
  running: boolean;
  error: string | null;
  runDemo: () => Promise<void>;
  reset: () => Promise<void>;
}

export function useDemoRun(onState: (next: DemoState) => void): DemoRunFlow {
  const [run, setRun] = useState<DemoRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const runDemo = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setRunning(true);
    setError(null);
    try {
      const result = await api.runDemo();
      setRun(result);
      onState(result.state);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Demo run failed.');
    } finally {
      setRunning(false);
      inFlight.current = false;
    }
  }, [onState]);

  const reset = useCallback(async () => {
    setError(null);
    try {
      onState(await api.resetDemo());
      setRun(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Demo reset failed.');
    }
  }, [onState]);

  return { run, running, error, runDemo, reset };
}
