// Purpose: authenticated, environment-gated route for the Interactive Analysis Lab.
// Responsibilities: render the lab only where it is explicitly enabled. The lab is an internal
//   fixture surface, not a production capability, so a disabled deployment returns a real 404
//   rather than hiding the entry point in navigation. Eligibility now also depends on the
//   deployment mode: development and test only, so the flag alone cannot expose it in a hosted
//   judge or production build. The backend gates /api/v1/analysis/* the same way.
import { notFound } from 'next/navigation';

import { AnalysisLab } from '@/components/analysis-lab/AnalysisLab';
import { analysisLabEnabled } from '@/services/deploymentMode';

export const metadata = {
  title: 'Interactive Analysis Lab · DeceptiForge',
};

export default function AnalysisLabPage() {
  if (!analysisLabEnabled()) {
    notFound();
  }
  return <AnalysisLab />;
}
