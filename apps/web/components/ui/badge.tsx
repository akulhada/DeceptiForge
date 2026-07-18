// Purpose: provide a compact status label primitive.
// Responsibilities: render tonal badges via variant classes shared across the dashboard.
import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium',
  {
    variants: {
      tone: {
        neutral: 'border-slate-700 bg-slate-800/60 text-slate-300',
        info: 'border-sky-800 bg-sky-950/50 text-sky-300',
        success: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
        warning: 'border-amber-800 bg-amber-950/50 text-amber-300',
        danger: 'border-red-800 bg-red-950/50 text-red-300',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
