// Purpose: lazily generate an AI investigation summary for one incident.
// Responsibilities: call the narrative endpoint only on demand, tracking loading, error, and the
//   returned narrative. Never auto-generates. Dependencies: the API client.
'use client';

import { useCallback, useState } from 'react';

import { api, ApiError } from '@/services/api';
import type { IncidentNarrative } from '@/services/types';

interface NarrativeState {
  narrative: IncidentNarrative | null;
  loading: boolean;
  error: string | null;
  generate: () => Promise<void>;
}

export function useIncidentNarrative(incidentId: string): NarrativeState {
  const [narrative, setNarrative] = useState<IncidentNarrative | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setNarrative(await api.generateIncidentNarrative(incidentId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Failed to generate the summary.');
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  return { narrative, loading, error, generate };
}
