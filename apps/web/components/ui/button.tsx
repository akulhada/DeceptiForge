// Purpose: provide the primary action-button primitive.
// Responsibilities: consistent button styling and disabled state across demo controls.
import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500',
  {
    variants: {
      variant: {
        primary: 'bg-sky-600 text-white hover:bg-sky-500',
        secondary: 'border border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700',
        ghost: 'text-slate-300 hover:bg-slate-800',
      },
      size: {
        md: 'h-9 px-4',
        sm: 'h-8 px-3 text-xs',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
