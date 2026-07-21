// Purpose: lazily generate an AI investigation summary for one incident.
// Responsibilities: call the narrative endpoint only on demand, tracking loading, error, and the
//   returned narrative. Never auto-generates. Dependencies: the API client.
'use client';

import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '@/services/api';
import type { IncidentNarrative } from '@/services/types';

interface NarrativeState {
  narrative: IncidentNarrative | null;
  loading: boolean;
  error: string | null;
  generate: () => Promise<void>;
}

export function useIncidentNarrative(
  incidentId: string,
  initialNarrative?: IncidentNarrative | null,
  generateNarrative?: (id: string) => Promise<IncidentNarrative>,
): NarrativeState {
  const [narrative, setNarrative] = useState<IncidentNarrative | null>(initialNarrative ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNarrative(initialNarrative ?? null);
    setError(null);
  }, [incidentId, initialNarrative]);

  const generate = useCallback(async () => {
    if (!generateNarrative) return;
    setLoading(true);
    setError(null);
    try {
      setNarrative(await generateNarrative(incidentId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Failed to generate the summary.');
    } finally {
      setLoading(false);
    }
  }, [generateNarrative, incidentId]);

  return { narrative, loading, error, generate };
}
