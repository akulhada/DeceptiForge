// Purpose: authenticated product route for the Interactive Analysis Lab (never under /demo).
// Responsibilities: render the lab, which resolves the tenant session and calls the org-scoped
//   /api/v1/analysis endpoints. Uses normal production authentication and organization context.
import { AnalysisLab } from '@/components/analysis-lab/AnalysisLab';

export const metadata = {
  title: 'Interactive Analysis Lab · DeceptiForge',
};

export default function AnalysisLabPage() {
  return <AnalysisLab />;
}
