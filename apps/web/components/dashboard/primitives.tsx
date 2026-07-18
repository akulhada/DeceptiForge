// Purpose: small shared layout helpers used across dashboard sections.
// Responsibilities: section framing and tag lists so sections stay declarative.
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';

export function Section({
  id,
  step,
  title,
  description,
  children,
}: {
  id: string;
  step: number;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <div className="mb-3 flex items-baseline gap-3">
        <span className="text-xs font-semibold text-sky-500">STEP {step}</span>
        <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      </div>
      {description ? <p className="mb-4 text-sm text-slate-400">{description}</p> : null}
      {children}
    </section>
  );
}

export function TagList({ items, empty = '—' }: { items: readonly string[]; empty?: string }) {
  if (items.length === 0) return <span className="text-xs text-slate-600">{empty}</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item}>{item}</Badge>
      ))}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-1 text-sm text-slate-200">{children}</div>
    </div>
  );
}
