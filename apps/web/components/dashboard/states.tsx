// Purpose: shared empty, error, and loading presentations for dashboard sections.
// Responsibilities: keep non-happy-path UI consistent. Dependencies: Card, Skeleton.
import type { ReactNode } from 'react';

import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-3 p-10 text-center">
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {hint ? <p className="max-w-md text-xs text-slate-500">{hint}</p> : null}
      {action}
    </Card>
  );
}

export function ErrorState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-3 border-red-900/60 bg-red-950/20 p-10 text-center">
      <p className="text-sm font-medium text-red-300">Something went wrong</p>
      <p className="max-w-md text-xs text-red-200/70">{message}</p>
      {action}
    </Card>
  );
}

export function LoadingState() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <Skeleton key={index} className="h-24" />
      ))}
    </div>
  );
}
