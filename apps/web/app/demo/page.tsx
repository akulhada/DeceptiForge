// Purpose: the curated fictional DeceptiForge story.
// Responsibilities: render the fixed narrative, and return a 404 when this build does not offer it.
// The gate is duplicated from the navigation deliberately: hiding a link is not a control, so the
// route refuses on its own rather than trusting that nothing linked to it.
import { notFound } from 'next/navigation';

import { DemoDashboard } from '@/components/demo/DemoDashboard';
import { demoEnabled } from '@/services/deploymentMode';

export default function DemoPage() {
  if (!demoEnabled()) notFound();
  return <DemoDashboard />;
}
