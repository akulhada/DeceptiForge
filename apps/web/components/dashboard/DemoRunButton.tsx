// Purpose: render the demo action controls (seed and simulate).
// Responsibilities: expose the two story-driving actions with pending labels. Dependencies: Button.
'use client';

import { Play, ShieldAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';

export function DemoRunButton({
  onSeed,
  onSimulate,
  seeding,
  simulating,
  canSimulate,
}: {
  onSeed: () => void;
  onSimulate: () => void;
  seeding: boolean;
  simulating: boolean;
  canSimulate: boolean;
}) {
  const pending = seeding || simulating;

  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={onSeed} disabled={pending}>
        <Play className="h-4 w-4" />
        {seeding ? 'Seeding…' : 'Seed demo data'}
      </Button>
      <Button onClick={onSimulate} disabled={pending || !canSimulate}>
        <ShieldAlert className="h-4 w-4" />
        {simulating ? 'Simulating…' : 'Simulate detection'}
      </Button>
    </div>
  );
}
