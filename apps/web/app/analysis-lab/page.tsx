// Purpose: authenticated, environment-gated route for the Interactive Analysis Lab.
// Responsibilities: render the lab only where it is explicitly enabled. The lab is a demonstration
//   and testing surface, not a production capability, so a disabled deployment returns a real 404
//   rather than hiding the entry point in navigation. The backend gates /api/v1/analysis/* the same
//   way, so neither surface can be reached alone.
import { notFound } from 'next/navigation';

import { AnalysisLab } from '@/components/analysis-lab/AnalysisLab';

// Enabled only when explicitly set. Production builds leave it unset, and the API refuses the
// matching backend flag outside development, so the two gates cannot drift apart silently.
const ANALYSIS_LAB_ENABLED = process.env.NEXT_PUBLIC_ANALYSIS_LAB_ENABLED === 'true';

export const metadata = {
  title: 'Interactive Analysis Lab · DeceptiForge',
};

export default function AnalysisLabPage() {
  if (!ANALYSIS_LAB_ENABLED) {
    notFound();
  }
  return <AnalysisLab />;
}
