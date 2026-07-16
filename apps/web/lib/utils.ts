// Purpose: provide shadcn-compatible class composition. Responsibilities: merge conditional Tailwind class names predictably. Future modules: keep this as the single styling utility unless a distinct concern emerges.
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
