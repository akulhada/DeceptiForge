// Purpose: load and hold the aggregate dashboard state.
// Responsibilities: fetch /demo/state, expose loading and error status, and allow other hooks to
//   replace the state after a demo action. Dependencies: the API client.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { api, ApiError } from '@/services/api';
import type { DemoState } from '@/services/types';

interface DashboardData {
  state: DemoState | null;
  loading: boolean;
  error: string | null;
  setState: (next: DemoState) => void;
  refetch: () => Promise<void>;
}

export function useDashboardData(): DashboardData {
  const [state, setState] = useState<DemoState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setState(await api.getState());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { state, loading, error, setState, refetch };
}
