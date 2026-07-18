// Purpose: provide a loading placeholder primitive.
// Responsibilities: render a pulsing block used by dashboard loading states.
import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('animate-pulse rounded-md bg-slate-800/70', className)} {...props} />;
}
