// Purpose: render one generated decoy with masked payload values.
// Responsibilities: show type, placement, template, trace, validation, and safety; keep secret
//   values hidden until the viewer reveals them. Dependencies: Card, Badge, types.
'use client';

import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Field } from './primitives';
import type { DecoyAsset } from '@/services/types';

const SENSITIVE_KEY = /value|secret|token|password|key|credential/i;

function renderValue(key: string, value: unknown, revealed: boolean): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (!revealed && SENSITIVE_KEY.test(key)) return '••••••••';
  return text;
}

export function DecoyCard({ asset }: { asset: DecoyAsset }) {
  const [revealed, setRevealed] = useState(false);
  const safe = asset.safety_metadata.safe_for_demo && !asset.safety_metadata.contains_real_credentials;

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info" className="uppercase">
            {asset.decoy_type}
          </Badge>
          <Badge>{asset.template_id}</Badge>
          <Badge tone={asset.validation.valid ? 'success' : 'danger'}>
            {asset.validation.valid ? 'valid' : 'invalid'}
          </Badge>
          <Badge tone={safe ? 'success' : 'warning'}>{safe ? 'inert' : 'review'}</Badge>
        </div>
        <button
          type="button"
          onClick={() => setRevealed((value) => !value)}
          className="text-xs text-sky-400 hover:underline"
        >
          {revealed ? 'Hide values' : 'Reveal values'}
        </button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Target placement">
          <span className="font-mono text-xs">{asset.target_location}</span>
        </Field>
        <Field label="Trace ID">
          <span className="font-mono text-xs text-sky-300">
            {asset.trigger_metadata.trace_identifier}
          </span>
        </Field>
      </div>

      <div className="mt-3">
        <p className="text-xs uppercase tracking-wide text-slate-500">Payload</p>
        <div className="mt-1 space-y-1 rounded-md border border-slate-800 bg-slate-950/60 p-2 font-mono text-xs">
          {Object.entries(asset.payload).map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <span className="text-slate-500">{key}:</span>
              <span className="break-all text-slate-300">{renderValue(key, value, revealed)}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
